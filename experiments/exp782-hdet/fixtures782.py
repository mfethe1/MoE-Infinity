#!/usr/bin/env python3
"""exp782 local fixture battery: synthetic out/ trees driving analyze782.py into
every branch. Runs on Mac python3 (no torch needed). Exit 0 only if all pass.
Derived from the exp760/exp781 fixture discipline: build out/ trees, invoke the
real analyzer, match exit code + key strings."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZER = os.path.join(HERE, "analyze782.py")
CELLS = os.path.join(HERE, "cells782.json")

REF = [list(range(1000 + 10 * i, 1000 + 10 * i + 64)) for i in range(6)]  # sealed ref streams


def write_refs(d):
    os.makedirs(os.path.join(d, "refs"), exist_ok=True)
    rows = [{"prompt_index": i, "out_ids": v, "out_sha": "x%d" % i} for i, v in enumerate(REF)]
    for n in ("RC_2.json", "RC_3.json"):
        json.dump({"rows": rows}, open(os.path.join(d, "refs", n), "w"))


def div_ids(diverged_idx, flip=1):
    v = [list(x) for x in REF]
    for i in diverged_idx:
        v[i][31] = v[i][31] + flip
    return v


def make_cell(d, cid, arm, mode, out_ids=None, banner=True, util=60.0, la=None,
              col=True, foreign=False, missing=False):
    if missing:
        return
    rows = [{"prompt_index": i, "out_ids": v, "out_sha": "s%d" % i}
            for i, v in enumerate(out_ids if out_ids is not None else REF)]
    json.dump({"rows": rows}, open(os.path.join(d, cid + ".json"), "w"))
    log = MODE_BANNER[mode] if banner else "exp752 mode=9"
    if not banner:
        log = "some other line"
    open(os.path.join(d, cid + ".log"), "w").write(log + "\nprompt 0: ok\n")
    with open(os.path.join(d, cid + ".util.csv"), "w") as f:
        for _ in range(20):
            f.write("t,%.1f\n" % util)
    # mon.csv: loadavg col + apps col; own pids appear for co-tenant when col=True
    la = la if la is not None else (2.0 if arm == "Q" else 12.0)
    own = set()
    with open(os.path.join(d, cid + ".mon.csv"), "w") as f:
        for _ in range(10):
            f.write("t,%.1f;1;1,0,0,\n" % la)
    if arm in ("G", "CG"):
        pid = "4242" if col else "59999"
        if col:
            open(os.path.join(d, cid + ".col.pid"), "w").write(pid + "\n")
            open(os.path.join(d, cid + ".col.log"), "w").write(
                "exp757-col pid=%s uuid=DF7C name=NVIDIA alloc_tensors=8 n=2048\n" % pid)
            own.add(pid)
        with open(os.path.join(d, cid + ".mon.csv"), "a") as f:
            f.write("t,%.1f;1;1,0,0,%s|%s|\n" % (la, pid, pid))
    if foreign:
        with open(os.path.join(d, cid + ".mon.csv"), "a") as f:
            f.write("t,%.1f;1;1,0,0,7777|\n" % la)


MODE_BANNER = {"H": "exp752 mode=0", "RC": "exp752 mode=2"}


def run_case(name, build, want_rc, want_sub):
    d = tempfile.mkdtemp(prefix="fx782-")
    try:
        os.makedirs(os.path.join(d, "out"))
        write_refs(d)
        shutil.copy(CELLS, os.path.join(d, "cells782.json"))
        build(d, os.path.join(d, "out"))
        p = subprocess.run([sys.executable, ANALYZER, os.path.join(d, "out"),
                            "--refs", os.path.join(d, "refs"),
                            "--cells", os.path.join(d, "cells782.json")],
                           capture_output=True, text=True)
        out = p.stdout + p.stderr
        ok_rc = (p.returncode == want_rc)
        ok_sub = (want_sub in out)
        status = "PASS" if (ok_rc and ok_sub) else "FAIL"
        print(f"[{status}] {name}: rc={p.returncode} (want {want_rc}); '{want_sub}' "
              f"{'found' if ok_sub else 'MISSING'}")
        if status == "FAIL":
            print(out[:2000])
            return False
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def full_tree(d, outdir, h_div, rc_div, h_valid=True, rc_valid=True):
    make_cell(outdir, "QH1", "Q", "H")
    make_cell(outdir, "QR1", "Q", "RC")
    hcells = [("GH1",), ("GH2",), ("GH3",), ("CH1",), ("CGH1",)]
    rccells = [("GR1",), ("CR1",), ("CGR1",)]
    for idx, (cid,) in enumerate(hcells):
        ids = div_ids([2]) if (h_valid and idx in h_div) else REF
        bad = (not h_valid) and idx == 0  # make first H cell invalid via banner
        make_cell(outdir, cid, "CG" if "CG" in cid else ("C" if "C" in cid else "G"), "H",
                  out_ids=ids, banner=not bad)
    for idx, (cid,) in enumerate(rccells):
        ids = div_ids([2]) if (rc_valid and idx in rc_div) else REF
        make_cell(outdir, cid, "CG" if "CG" in cid else ("C" if "C" in cid else "G"), "RC",
                  out_ids=ids)


cases = []
cases.append(("rc1 H-unstable RC-stable", lambda d, o: full_tree(d, o, h_div=[0, 2], rc_div=[]),
              1, "H-UNSTABLE-RC-STABLE"))
cases.append(("rc2 both unstable", lambda d, o: full_tree(d, o, h_div=[0], rc_div=[1]),
              2, "BOTH-UNSTABLE"))
cases.append(("rc3 RC-unstable only", lambda d, o: full_tree(d, o, h_div=[], rc_div=[0]),
              3, "RC-UNSTABLE-H-STABLE"))
cases.append(("rc7 both stable", lambda d, o: full_tree(d, o, h_div=[], rc_div=[]),
              7, "BOTH-STABLE"))
cases.append(("anchor-fail H", lambda d, o: (full_tree(d, o, [], []),
              make_cell(o, "QH1", "Q", "H", out_ids=div_ids([1]))), 2, "ANCHOR-FAIL (QH1"))
cases.append(("anchor-fail RC", lambda d, o: (full_tree(d, o, [], []),
              make_cell(o, "QR1", "Q", "RC", out_ids=div_ids([4]))), 2, "ANCHOR-FAIL (QR1"))
cases.append(("refs disagree = fatal", lambda d, o: (full_tree(d, o, [], []),
              json.dump({"rows": [{"out_ids": [1]}]}, open(os.path.join(d, "refs", "RC_3.json"), "w"))),
              None, None))


def case_refs_disagree(d, o):
    pass


# handle refs-disagree separately (SystemExit path)
def run_all():
    ok = 0
    for name, build, want_rc, want_sub in cases:
        if want_rc is None:
            d = tempfile.mkdtemp(prefix="fx782-")
            try:
                os.makedirs(os.path.join(d, "out"))
                write_refs(d)
                shutil.copy(CELLS, os.path.join(d, "cells782.json"))
                build(d, os.path.join(d, "out"))
                p = subprocess.run([sys.executable, ANALYZER, os.path.join(d, "out"),
                                    "--refs", os.path.join(d, "refs"),
                                    "--cells", os.path.join(d, "cells782.json")],
                                   capture_output=True, text=True)
                good = p.returncode != 0 and "sealed refs" in (p.stdout + p.stderr)
                print("[%s] %s" % ("PASS" if good else "FAIL", name))
                ok += bool(good)
            finally:
                shutil.rmtree(d, ignore_errors=True)
            continue
        ok += run_case(name, build, want_rc, want_sub)

    def build_invalid(d, o):
        full_tree(d, o, [], [])
        for cid in ("GH1", "GH2", "GH3", "CH1", "CGH1"):
            open(os.path.join(o, cid + ".log"), "w").write("no banner here\n")

    ok += run_case("data-fail all H contended invalid", build_invalid, 9, "DATA-FAIL")

    def build_foreign(d, o):
        full_tree(d, o, [0], [])
        make_cell(o, "GR1", "G", "RC", out_ids=REF, foreign=True)

    ok += run_case("foreign app excludes cell (still rc1)",
                   build_foreign, 1, "foreign-app")

    def build_noqr(d, o):
        full_tree(d, o, [], [])
        os.remove(os.path.join(o, "QR1.json"))

    ok += run_case("invalid RC anchor warns, proceeds", build_noqr, 7, "WARN: anchor QR1 invalid")

    def build_bannermismatch(d, o):
        full_tree(d, o, [1], [])
        open(os.path.join(o, "GH1.col.log"), "w").write(
            "exp757-col pid=111111 uuid=DF7C alloc_tensors=8 n=2048\n")

    ok += run_case("col banner pid mismatch excludes cell (still rc1)",
                   build_bannermismatch, 1, "col-banner-pid-mismatch")
    print("SUMMARY: %d/%d PASS" % (ok, 11))
    return 0 if ok == 11 else 1


if __name__ == "__main__":
    sys.exit(run_all())
