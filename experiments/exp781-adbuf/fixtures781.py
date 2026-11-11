#!/usr/bin/env python3
"""exp781 analyzer fixture battery (synthetic out/ trees, frozen gates)."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_ROWS = [{"n_new": 64, "t_1tok_s": 0.5, "t_full_s": 7.0, "out_sha": f"r{i:02d}x"} for i in range(24)]


def W_of(rows):
    return sum(r["t_1tok_s"] + r["t_full_s"] for r in rows)


def mk(root, wa_rows=None, wb_rows=None, banner=False, rcs=("PY_ADBUF RC=0", "PY_BLOCK RC=0"),
       bad_banner=False, wa_res=None, wb_res=None):
    out = os.path.join(root, "out"); os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "SRC_HEAD.txt"), "w").write("b7f6ca4d2caa5229698d78deb03b454fc20947dd\n")
    open(os.path.join(out, "ENV.txt"), "w").write("moei-RC753 x y\ntorch 2.11.0+cu128\nmoei-776 /home/mfeth/exp776/src776/moe_infinity\n")
    open(os.path.join(out, "SRC776_FILE_SHA.txt"), "w").write("3571f714c811e1c7\n")
    open(os.path.join(out, "ENGB_SHA.txt"), "w").write("c62edffe2d750e8e\n")
    open(os.path.join(out, "CELL_RC.txt"), "w").write("\n".join(rcs) + "\n")
    open(os.path.join(out, "BADIO"), "w").write("")
    if banner:
        open(os.path.join(out, "BANNER-FAIL"), "w").write("x")
    ra = dict(wa_res or {}); rb = dict(wb_res or {})
    ra.setdefault("rows", wa_rows if wa_rows is not None else BASE_ROWS); ra["env_db"] = "1"
    rb.setdefault("rows", wb_rows if wb_rows is not None else BASE_ROWS); rb["env_db"] = "0"
    json.dump(ra, open(os.path.join(out, "PY_ADBUF.json"), "w"))
    json.dump(rb, open(os.path.join(out, "PY_BLOCK.json"), "w"))
    open(os.path.join(out, "PY_ADBUF.log"), "w").write("exp781 db=1 ok=True\n" + ("BAD" if bad_banner else ""))
    open(os.path.join(out, "PY_BLOCK.log"), "w").write("exp781 db=0 ok=True\n" + ("BAD" if bad_banner else ""))


def scale(w_target):
    per = w_target / 24.0
    return [{"n_new": 64, "t_1tok_s": per * 0.4, "t_full_s": per * 0.6, "out_sha": f"r{i:02d}x"} for i in range(24)]


def run_case(name, expect, **kw):
    root = tempfile.mkdtemp(prefix="fx781_")
    try:
        mk(root, **kw)
        v = os.path.join(root, "v"); os.makedirs(v, exist_ok=True)
        p = subprocess.run([sys.executable, os.path.join(HERE, "analyze781.py"), root, v],
                           capture_output=True, text=True)
        got = None
        for ln in (p.stdout or "").splitlines():
            if ln.startswith("rc="):
                got = int(ln[3:])
        ok = got == expect
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={got}")
        return ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


CASES = [
    ("large-overlap", 1, dict(wa_rows=scale(160.0), wb_rows=scale(196.0))),          # delta .1837
    ("mild", 2, dict(wa_rows=scale(185.0), wb_rows=scale(199.0))),                   # delta .0704
    ("no-move", 7, dict(wa_rows=scale(185.0), wb_rows=scale(190.0))),                # delta .0263
    ("boundary-0.15", 1, dict(wa_rows=scale(161.5), wb_rows=scale(190.0))),          # delta .15
    ("adbuf-regression", 3, dict(wa_rows=scale(198.0), wb_rows=scale(188.0))),       # delta -.0532
    ("large-regression", 5, dict(wa_rows=scale(210.0), wb_rows=scale(184.0))),       # delta -.1413
    ("nnew-fail", 9, dict(wb_rows=[dict(r, n_new=63) for r in scale(190.0)])),
    ("cov-fail", 9, dict(wa_rows=scale(100.0), wb_rows=scale(190.0))),
    ("banner-fail", 9, dict(banner=True)),
    ("rc-fail", 9, dict(rcs=("PY_ADBUF RC=3", "PY_BLOCK RC=0"))),
]
if __name__ == "__main__":
    res = [run_case(n, e, **k) for n, e, k in CASES]
    print(f"{sum(res)}/{len(res)}")
    sys.exit(0 if all(res) else 1)
