#!/usr/bin/env python3
"""exp784 fixtures: synthetic analyzer batteries. Usage: python3 fixtures784.py"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

def cell(arm, ratio, tps, sha, mode=None, offload=None, res_ratio=None, nrow=None):
    mode = mode or ("uniform_fp8" if arm == "F" else "legacy")
    offload = offload or ("/home/mfeth/moe-offload-fp8" if arm == "F" else "/home/mfeth/moe-offload")
    rr = res_ratio if res_ratio is not None else ratio
    rows = [{"i": i, "decode_tok_s": t, "out_sha": sha + f"{i:02d}", "out_ids": [sha, i]}
            for i, t in enumerate(tps)]
    if nrow is not None:
        rows = rows[:nrow]
    return {"res": {"resident_mode": mode, "offload": offload, "ratio": rr, "load_s": 25.0},
            "rows": rows}

def build(root, mk, skip=()):
    os.makedirs(os.path.join(root, "out"), exist_ok=True)
    for cid in CELLS:
        if cid in skip:
            continue
        with open(os.path.join(root, "out", cid + ".json"), "w") as f:
            json.dump(mk(cid), f)

R25, R50 = 0.25, 0.50
CELLS = {"B25a": ("B", R25), "B25b": ("B", R25), "F25a": ("F", R25), "F25b": ("F", R25),
         "B50a": ("B", R50), "B50b": ("B", R50), "F50a": ("F", R50), "F50b": ("F", R50)}
TPS = [10.0, 10.2, 9.8]

def base(b25, f25, b50, f50):
    def mk(cid):
        arm, ratio = CELLS[cid]
        k = arm + str(int(ratio * 100))
        t = {"B25": b25, "F25": f25, "B50": b50, "F50": f50}[k]
        return cell(arm, ratio, t, k)
    return mk

CASES = [
    ("ok-major-at-25", lambda r: build(r, base(TPS, [t * 1.8 for t in TPS], TPS, TPS)), 1),
    ("ok-mild-at-50", lambda r: build(r, base(TPS, TPS, TPS, [t * 1.2 for t in TPS])), 2),
    ("ok-nomove", lambda r: build(r, base(TPS, [t * 1.04 for t in TPS], TPS, [t * 0.97 for t in TPS])), 3),
    ("negative-is-nomove", lambda r: build(r, base(TPS, [t * 0.85 for t in TPS], TPS, TPS)), 3),
    ("missing-cell", lambda r: build(r, base(TPS, TPS, TPS, TPS), skip=("F50b",)), 9),
    ("ratio-mismatch", lambda r: build(r, (lambda c: cell(CELLS[c][0], CELLS[c][1], TPS, c, res_ratio=0.9))), 9),
    ("mode-mismatch", lambda r: build(r, (lambda c: cell(CELLS[c][0], CELLS[c][1], TPS, c,
                                                          mode="legacy" if CELLS[c][0] == "F" else "uniform_fp8"))), 9),
    ("wrong-store", lambda r: build(r, (lambda c: cell(CELLS[c][0], CELLS[c][1], TPS, c,
                                                        offload="/home/mfeth/moe-offload" if CELLS[c][0] == "F" else "/home/mfeth/moe-offload-fp8"))), 9),
    ("b-nondet", lambda r: build(r, (lambda c: cell(CELLS[c][0], CELLS[c][1], TPS, c + "x"))), 9),
    ("f-nondet-rc5", lambda r: build(r, (lambda c: cell(CELLS[c][0], CELLS[c][1], TPS,
                                                         c + "x" if CELLS[c][0] == "F" else "bdet"))), 5),
    ("short-rows", lambda r: build(r, (lambda c: cell(CELLS[c][0], CELLS[c][1], TPS, c, nrow=1))), 9),
    ("cross-arm-same-shas-still-nomove", lambda r: build(r, (lambda c: cell(CELLS[c][0], CELLS[c][1], TPS, "same"))), 3),
]

def run(root):
    r = subprocess.run([sys.executable, os.path.join(HERE, "analyze784.py"), root],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("VERDICT"):
            return int(line.split("=")[1])
    raise SystemExit(f"no verdict: {r.stdout[-200:]} {r.stderr[-200:]}")

def main():
    tmp = tempfile.mkdtemp(prefix="fx784-")
    npass = 0
    for name, setup, want in CASES:
        d = os.path.join(tmp, name)
        os.makedirs(d)
        setup(d)
        got = run(d)
        ok = got == want
        npass += ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: rc={got} want={want}")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"SUMMARY {npass}/{len(CASES)}")
    sys.exit(0 if npass == len(CASES) else 1)

if __name__ == "__main__":
    main()
