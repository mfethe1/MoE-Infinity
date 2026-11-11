#!/usr/bin/env python3
"""fixtures771.py — battery for analyze771.py (collapsed-stack synthetic arms)."""
import json, os, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze771.py")

def mk(d, arm, W, stacks):
    """stacks: list of (func, samples). Emits one collapsed line per func."""
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    rows = [{"t_1tok_s": 0.5, "t_full_s": W / 6.0, "win_full": [100.0 + i * 10, 110.0 + i * 10], "decode_tok_s": 11.0} for i in range(6)]
    json.dump({"rows": rows}, open(os.path.join(d, "out", arm + ".json"), "w"))
    with open(os.path.join(d, "out", arm + ".pyspy"), "w") as f:
        f.write("engine (engine.py:60);decode (engine.py:120) 0\n")  # separator junk line with 0
        for func, n in stacks:
            f.write(f"engine (engine.py:60);decode (engine.py:120);{func} {n}\n")
        f.write("\n# comment line ; with semicolon\n")

def build(src="b7f6ca4d2caa5229698d78deb03b454fc20947dd"):
    d = tempfile.mkdtemp(prefix="f771-")
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    open(os.path.join(d, "out", "SRC_HEAD.txt"), "w").write(src + "\n")
    return d

def run(d):
    r = subprocess.run([sys.executable, AN, d, d], capture_output=True, text=True)
    rc = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="):
            rc = int(ln[3:])
    return rc, r.stdout + r.stderr

R = 50  # samples per second

CASES = [
    # name, expect_rc, grep, lgc_stacks, spec_stacks
    ("f-top", 1, "F-TOP",
     [("f_base (b.py:1)", 3000), ("g (g.py:2)", 1500)],
     [("f_base (b.py:1)", 3000), ("g (g.py:2)", 1500), ("predictor (p.py:9)", 500)]),  # +10s, predictor all
    ("f-pair", 2, "F-PAIR",
     [("f_base (b.py:1)", 3000)],
     [("f_base (b.py:1)", 3000), ("predictor (p.py:9)", 132), ("dispatch (d.py:4)", 113), ("extra (e.py:7)", 130)]),  # +7.5s, top1 35% <40%, pair 65% >=60%
    ("f-diffuse", 7, "F-DIFFUSE",
     [("f_base (b.py:1)", 3000)],
     [("f_base (b.py:1)", 3000), ("a (a.py:1)", 110), ("b (b.py:2)", 110), ("c (c.py:3)", 110), ("d (d.py:4)", 110), ("e (e.py:5)", 110)]),  # +11s over 5
    ("no-signal", 5, "NO-SIGNAL",
     [("f_base (b.py:1)", 3000)], [("f_base (b.py:1)", 3050)]),  # +1s
    ("reversed", 8, "REVERSED",
     [("f_base (b.py:1)", 3600)], [("f_base (b.py:1)", 3000)]),  # -12s
    ("identify-fail", 9, "IDENTIFY-FAIL",
     [("f_base (b.py:1)", 3000)], [("f_base (b.py:1)", 3600)]),
    ("data-fail-short", 4, "DATA-FAIL",
     [("f_base (b.py:1)", 30)], [("f_base (b.py:1)", 3600)]),
    ("data-fail-missing", 4, "MISSING",
     [("f_base (b.py:1)", 3000)], None),
]

def main():
    n_ok = 0
    for name, expect, grep, lgc, spec in CASES:
        d = build("deadbeef" if name == "identify-fail" else "b7f6ca4d2caa5229698d78deb03b454fc20947dd")
        mk(d, "PY_LGC", 36.0, lgc)
        if spec is not None:
            mk(d, "PY_SPEC", 43.0, spec)
        else:
            os.makedirs(os.path.join(d, "out"), exist_ok=True)
            open(os.path.join(d, "out", "PY_SPEC.pyspy"), "w").write("")
        rc, out = run(d)
        ok = rc == expect and (grep is None or grep in out)
        n_ok += ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep={grep!r} {'found' if grep in out else 'MISSING'}")
        if not ok:
            print(out[:600])
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{n_ok}/{len(CASES)} PASS")
    return 0 if n_ok == len(CASES) else 1

if __name__ == "__main__":
    sys.exit(main())
