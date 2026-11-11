#!/usr/bin/env python3
"""exp783 fixtures: synthetic analyzer batteries. Usage: python3 fixtures783.py"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

def cell(cid, arm, tps, sha, mode=None, offload=None, nrow=None):
    mode = mode or ("uniform_fp8" if arm == "F" else "legacy")
    offload = offload or ("/home/mfeth/moe-offload-fp8" if arm == "F" else "/home/mfeth/moe-offload")
    n = len(tps) if nrow is None else nrow
    rows = [{"i": i, "decode_tok_s": t, "out_sha": sha + f"{i:02d}", "out_ids": [sha, i]}
            for i, t in enumerate(tps)]
    return {"res": {"resident_mode": mode, "offload": offload, "load_s": 25.0}, "rows": rows[:n]}

def build(root, b1, b2, f1, f2, skip=()):
    os.makedirs(os.path.join(root, "out"), exist_ok=True)
    for cid, d in (("B1", b1), ("B2", b2), ("F1", f1), ("F2", f2)):
        if cid in skip:
            continue
        with open(os.path.join(root, "out", cid + ".json"), "w") as f:
            json.dump(d, f)

def run(root):
    r = subprocess.run([sys.executable, os.path.join(HERE, "analyze783.py"), root],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("VERDICT"):
            return int(line.split("=")[1])
    raise SystemExit(f"no verdict: {r.stdout[-200:]} {r.stderr[-200:]}")

TPS_B = [10.0, 10.2, 9.8, 10.1]
CASES = [
    ("ok-major", lambda r: build(r, cell("B1", "B", TPS_B, "b"), cell("B2", "B", TPS_B, "b"),
                                 cell("F1", "F", [t * 1.6 for t in TPS_B], "f"),
                                 cell("F2", "F", [t * 1.6 for t in TPS_B], "f")), 1),
    ("ok-mild", lambda r: build(r, cell("B1", "B", TPS_B, "b"), cell("B2", "B", TPS_B, "b"),
                                cell("F1", "F", [t * 1.2 for t in TPS_B], "f"),
                                cell("F2", "F", [t * 1.2 for t in TPS_B], "f")), 2),
    ("ok-nomove", lambda r: build(r, cell("B1", "B", TPS_B, "b"), cell("B2", "B", TPS_B, "b"),
                                  cell("F1", "F", [t * 1.03 for t in TPS_B], "f"),
                                  cell("F2", "F", [t * 1.03 for t in TPS_B], "f")), 3),
    ("negative-is-nomove", lambda r: build(r, cell("B1", "B", TPS_B, "b"), cell("B2", "B", TPS_B, "b"),
                                           cell("F1", "F", [t * 0.8 for t in TPS_B], "f"),
                                           cell("F2", "F", [t * 0.8 for t in TPS_B], "f")), 3),
    ("missing-f1", lambda r: build(r, cell("B1", "B", TPS_B, "b"), cell("B2", "B", TPS_B, "b"),
                                   cell("F1", "F", TPS_B, "f"), cell("F2", "F", TPS_B, "f"),
                                   skip=("F1",)), 9),
    ("mode-mismatch", lambda r: build(r, cell("B1", "B", TPS_B, "b"), cell("B2", "B", TPS_B, "b"),
                                      cell("F1", "F", TPS_B, "f", mode="legacy"),
                                      cell("F2", "F", TPS_B, "f")), 9),
    ("wrong-store-fp8", lambda r: build(r, cell("B1", "B", TPS_B, "b"), cell("B2", "B", TPS_B, "b"),
                                        cell("F1", "F", TPS_B, "f", offload="/home/mfeth/moe-offload"),
                                        cell("F2", "F", TPS_B, "f")), 9),
    ("wrong-store-bf16", lambda r: build(r, cell("B1", "B", TPS_B, "b", offload="/home/mfeth/moe-offload-fp8"),
                                         cell("B2", "B", TPS_B, "b"),
                                         cell("F1", "F", TPS_B, "f"), cell("F2", "F", TPS_B, "f")), 9),
    ("b-arm-nondet", lambda r: build(r, cell("B1", "B", TPS_B, "b1"), cell("B2", "B", TPS_B, "b2"),
                                     cell("F1", "F", TPS_B, "f"), cell("F2", "F", TPS_B, "f")), 9),
    ("f-arm-nondet-rc5", lambda r: build(r, cell("B1", "B", TPS_B, "b"), cell("B2", "B", TPS_B, "b"),
                                         cell("F1", "F", TPS_B, "f1"), cell("F2", "F", TPS_B, "f2")), 5),
    ("short-rows", lambda r: build(r, cell("B1", "B", TPS_B, "b", nrow=1), cell("B2", "B", TPS_B, "b"),
                                   cell("F1", "F", TPS_B, "f"), cell("F2", "F", TPS_B, "f")), 9),
]

def main():
    tmp = tempfile.mkdtemp(prefix="fx783-")
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
