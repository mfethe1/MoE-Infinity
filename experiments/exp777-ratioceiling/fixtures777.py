#!/usr/bin/env python3
"""fixtures777.py — battery for analyze777.py."""
import json, os, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze777.py")
ENVLINE = "moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py\nmoei-776 /home/mfeth/exp776/src776/moe_infinity/__init__.py\ntorch 2.x\n"

def build(rcs, Ws, badio="", sha="3571f714c811e1c7", src="b7f6ca4d2caa5229698d78deb03b454fc20947dd", env=ENVLINE):
    d = tempfile.mkdtemp(prefix="f777-")
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    open(os.path.join(d, "out", "SRC_HEAD.txt"), "w").write(src + "\n")
    open(os.path.join(d, "out", "ENV.txt"), "w").write(env)
    open(os.path.join(d, "out", "BADIO"), "w").write(badio)
    open(os.path.join(d, "out", "SRC776_FILE_SHA.txt"), "w").write(sha + "\n")
    with open(os.path.join(d, "out", "CELL_RC.txt"), "w") as f:
        for cid, rc in rcs.items():
            f.write(f"{cid} RC={rc}\n")
    for cid, W in Ws.items():
        if W is None:
            continue
        rows = [{"t_1tok_s": 0.5, "t_full_s": (W / 24.0) - 0.5, "n_new": 64} for _ in range(24)]
        json.dump({"rows": rows}, open(os.path.join(d, "out", cid + ".json"), "w"))
    return d

def run(d):
    r = subprocess.run([sys.executable, AN, d, d], capture_output=True, text=True)
    rc = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="):
            rc = int(ln[3:])
    return rc, r.stdout + r.stderr

CELLS = ["PY_R075", "PY_R090", "PY_R0975", "PY_R100"]
ok0 = {c: 0 for c in CELLS}

def main():
    n_ok = total = 0
    cases = [
        # name, expect_rc, grep, rcs, Ws
        ("large-headroom", 1, "LARGE-HEADROOM", ok0, {"PY_R075": 180, "PY_R090": 165, "PY_R0975": 150, "PY_R100": 140}),
        ("mild-headroom", 2, "MILD-HEADROOM", ok0, {"PY_R075": 180, "PY_R090": 178, "PY_R0975": 175, "PY_R100": 172}),
        ("no-headroom", 7, "NO-HEADROOM", ok0, {"PY_R075": 180, "PY_R090": 179, "PY_R0975": 177, "PY_R100": 176}),
        ("r100-fails-r0975-works", 2, "MILD-HEADROOM", {**ok0, "PY_R100": 1}, {"PY_R075": 180, "PY_R090": 176, "PY_R0975": 170}),
        ("covariate-fail", 4, "DATA-FAIL", ok0, {"PY_R075": 300, "PY_R090": 290, "PY_R0975": 280, "PY_R100": 270}),
        ("ref-cell-dirty", 4, "DATA-FAIL", {**ok0, "PY_R075": 2}, {"PY_R075": 180, "PY_R100": 140}),
        ("no-feasible-high-r", 4, "DATA-FAIL", {**ok0, "PY_R090": 1, "PY_R0975": 1, "PY_R100": 1}, {"PY_R075": 180}),
        ("badio", 4, "DATA-FAIL", dict(ok0, __badio="PY_R090 oscsv-empty\n"), {"PY_R075": 180, "PY_R100": 140}),
        ("identify-sha", 9, "IDENTIFY-FAIL", dict(ok0, __sha="deadbeefdeadbeef"), {"PY_R075": 180, "PY_R100": 140}),
    ]
    for name, expect, grep, kw, Ws in cases:
        extra = {k[2:]: v for k, v in kw.items() if k.startswith("__")}
        kw2 = {k: v for k, v in kw.items() if not k.startswith("__")}
        d = build(kw2, Ws, **extra)
        rc, out = run(d)
        ok = rc == expect and grep in out
        n_ok += ok; total += 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok: print(out[-500:])
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{n_ok}/{total} PASS")
    return 0 if n_ok == total else 1

if __name__ == "__main__":
    sys.exit(main())
