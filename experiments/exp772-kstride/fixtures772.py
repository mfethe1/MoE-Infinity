#!/usr/bin/env python3
"""fixtures772.py — battery for analyze772.py (3-arm synthetic dirs)."""
import json, os, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze772.py")
ENVLINE = "moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py\nmoei-772 /home/mfeth/exp772/src772/moe_infinity/__init__.py\ntorch 2.x\n"

def mk(d, arm, W, samples, spec):
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    rows = [{"t_1tok_s": 0.5, "t_full_s": W / 6.0, "decode_tok_s": 10.0 + arm_hash(arm)} for _ in range(6)]
    json.dump({"rows": rows}, open(os.path.join(d, "out", arm + ".json"), "w"))
    other = samples - spec
    with open(os.path.join(d, "out", arm + ".pyspy"), "w") as f:
        f.write(f"engine (engine.py:60);decode (engine.py:120) {other}\n")
        if spec:
            f.write(f"engine (engine.py:60);ExpertPrefetcher.speculative_prefetch (expert_prefetcher.py:450) {spec}\n")

def arm_hash(a):
    return {"PY_LGC": 2.0, "PY_SPEC": 0.0, "PY_K4": 1.5}[a]

def build(src="b7f6ca4d2caa5229698d78deb03b454fc20947dd", env=ENVLINE, badio=""):
    d = tempfile.mkdtemp(prefix="f772-")
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    open(os.path.join(d, "out", "SRC_HEAD.txt"), "w").write(src + "\n")
    open(os.path.join(d, "out", "ENV.txt"), "w").write(env)
    open(os.path.join(d, "out", "BADIO"), "w").write(badio)
    return d

def run(d):
    r = subprocess.run([sys.executable, AN, d, d], capture_output=True, text=True)
    rc = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="):
            rc = int(ln[3:])
    return rc, r.stdout + r.stderr

R = 50
BASE_S, BASE_SPEC = 3800, 0  # LGC: no spec leaf

def spec_cell(DW, leaf):
    return 3800 + int(DW * R), leaf

CASES = [
    # name, expect, grep, lgc(W,leaf), spec(W,leaf_s), k4(W,leaf_s)
    ("recover", 1, "RECOVER", (36.0, 0), (44.0, 5.3 * R), (37.0, 1.2 * R)),          # D=8, R=0.875, leaf 0.23
    ("recover-leaf-fail", 2, "PARTIAL", (36.0, 0), (44.0, 5.3 * R), (37.0, 3.2 * R)), # R=.875 but leaf 0.60>0.5
    ("partial", 2, "PARTIAL", (36.0, 0), (44.0, 5.3 * R), (40.5, 1.5 * R)),           # R=0.4375
    ("no-gain", 7, "NO-GAIN", (36.0, 0), (44.0, 5.3 * R), (43.5, 2.0 * R)),           # R=0.0625
    ("regress", 8, "REGRESS", (36.0, 0), (44.0, 5.3 * R), (47.5, 1.0 * R)),           # K4-SPEC=+3.5s
    ("no-baseline", 5, "NO-BASELINE", (36.0, 0), (36.5, 0.5 * R), (36.2, 0.1 * R)),   # D=0.5s
]

def main():
    n_ok = 0
    cases = list(CASES)
    for name, expect, grep, lgc, spec, k4 in cases:
        d = build()
        mk(d, "PY_LGC", lgc[0], BASE_S, 0)
        mk(d, "PY_SPEC", spec[0], 3800 + int((spec[0] - 36.0) * R), int(spec[1]))
        mk(d, "PY_K4", k4[0], 3800 + int((k4[0] - 36.0) * R), int(k4[1]))
        rc, out = run(d)
        ok = rc == expect and grep in out
        n_ok += ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok:
            print(out[-500:])
        shutil.rmtree(d, ignore_errors=True)
    extra = [
        ("identify-fail", 9, "IDENTIFY-FAIL", dict(src="deadbeef")),
        ("env-fail", 9, "IDENTIFY-FAIL", dict(env="moei-RC753 only\n")),
        ("data-fail", 4, "DATA-FAIL", dict(badio="PY_K4 pyspy-empty\n")),
    ]
    for name, expect, grep, kw in extra:
        d = build(**kw)
        mk(d, "PY_LGC", 36.0, BASE_S, 0)
        mk(d, "PY_SPEC", 44.0, 3800 + 8 * R, int(5.3 * R))
        mk(d, "PY_K4", 37.0, 3800 + R, int(1.2 * R))
        rc, out = run(d)
        ok = rc == expect and grep in out
        n_ok += ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok:
            print(out[-400:])
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{n_ok}/{len(cases)+len(extra)} PASS")
    return 0 if n_ok == len(cases) + len(extra) else 1

if __name__ == "__main__":
    sys.exit(main())
