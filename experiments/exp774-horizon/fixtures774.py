#!/usr/bin/env python3
"""fixtures774.py — battery for analyze774.py (3-arm synthetic dirs, 24 rows)."""
import json, os, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze774.py")
ENVLINE = "moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py\nmoei-774 /home/mfeth/exp774/src774/moe_infinity/__init__.py\ntorch 2.x\n"
SPECLEAF = "ExpertPrefetcher.speculative_prefetch (expert_prefetcher.py:450)"
DISPATCH = "ExpertPrefetcher._dispatch_eager_local (expert_prefetcher.py:320)"
DECODE = "decode (engine.py:120)"

def mk(d, arm, W, leaves):
    """leaves: dict leaf->samples (stacks are engine;leaf, two frames)."""
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    rows = [{"t_1tok_s": 0.5, "t_full_s": W / 24.0, "decode_tok_s": 10.0} for _ in range(24)]
    json.dump({"rows": rows}, open(os.path.join(d, "out", arm + ".json"), "w"))
    with open(os.path.join(d, "out", arm + ".pyspy"), "w") as f:
        for leaf, n in leaves.items():
            f.write(f"engine (engine.py:60);{leaf} {n}\n")

def base_leaves(W, spec_s, extra=None):
    lv = {DECODE: 3800 + int((W - 144.0) * 50)}
    if spec_s:
        lv[SPECLEAF] = int(spec_s)
    if extra:
        for k, v in extra.items():
            lv[k] = lv.get(k, 0) + v
    return lv

def build(src="b7f6ca4d2caa5229698d78deb03b454fc20947dd", env=ENVLINE, badio=""):
    d = tempfile.mkdtemp(prefix="f774-")
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

# 4x-horizon walls: LGC 182, SPEC 216 (D=34), tau_w=5
CASES = [
    # name, expect, grep, lgc(W,spec), spec(W,spec), db(W,spec), db_extra_leaves
    ("recover", 1, "RECOVER", (182.0, 0), (216.0, 21.0), (187.0, 4.0), None),            # D=34, R=0.853
    ("recover-leaf-fail", 2, "PARTIAL", (182.0, 0), (216.0, 21.0), (187.0, 13.0), None),  # R=.853 leaf .62
    ("partial", 2, "PARTIAL", (182.0, 0), (216.0, 21.0), (201.0, 5.0), None),             # R=0.441
    ("no-gain", 7, "NO-GAIN", (182.0, 0), (216.0, 21.0), (214.0, 6.0), None),             # R=0.059
    ("regress", 8, "REGRESS", (182.0, 0), (216.0, 21.0), (224.0, 4.0), None),             # DB-SPEC=+8 > 5
    ("no-baseline", 5, "NO-BASELINE", (182.0, 0), (183.0, 2.0), (182.5, 0.4), None),      # D=1 <= 5
    # attribution cases use explicit DB leaf dicts: DECODE delta +250, SPECLEAF +200
    # attr-carrier: DISPATCH +350 -> net 800, gate max(75,240)=240 < 350 -> CARRIER named
    ("attr-carrier", 7, "RESIDUAL-CARRIER: " + DISPATCH, (182.0, 0), (216.0, 21.0), None, {DECODE: 5950, SPECLEAF: 200, DISPATCH: 350}),
    # attr-diffuse: DECODE delta 0, five leaves +100 -> net 700, gate 210 > 100 -> DIFFUSE
    ("attr-diffuse", 7, "RESIDUAL-DIFFUSE", (182.0, 0), (216.0, 21.0), None, {DECODE: 5700, SPECLEAF: 200, "a (a.py:1)": 100, "b (b.py:2)": 100, "c (c.py:3)": 100, "d (d.py:4)": 100, "e (e.py:5)": 100}),
]

def main():
    n_ok = 0
    cases = list(CASES)
    for name, expect, grep, lgc, spec, db, extra in cases:
        d = build()
        mk(d, "PY_LGC", lgc[0], base_leaves(lgc[0], lgc[1] * 50))
        mk(d, "PY_SPEC", spec[0], base_leaves(spec[0], spec[1] * 50))
        if db is None:
            mk(d, "PY_DB", 214.0, extra)  # attribution cases: explicit leaves, no-gain wall
        else:
            mk(d, "PY_DB", db[0], base_leaves(db[0], db[1] * 50, extra))
        rc, out = run(d)
        ok = rc == expect and grep in out
        n_ok += ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok:
            print(out[-600:])
        shutil.rmtree(d, ignore_errors=True)
    extra_cases = [
        ("identify-fail", 9, "IDENTIFY-FAIL", dict(src="deadbeef")),
        ("env-fail", 9, "IDENTIFY-FAIL", dict(env="moei-RC753 only\n")),
        ("data-fail", 4, "DATA-FAIL", dict(badio="PY_DB pyspy-empty\n")),
    ]
    for name, expect, grep, kw in extra_cases:
        d = build(**kw)
        mk(d, "PY_LGC", 182.0, base_leaves(182.0, 0))
        mk(d, "PY_SPEC", 216.0, base_leaves(216.0, 21.0 * 50))
        mk(d, "PY_DB", 187.0, base_leaves(187.0, 4.0 * 50))
        rc, out = run(d)
        ok = rc == expect and grep in out
        n_ok += ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok:
            print(out[-400:])
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{n_ok}/{len(cases)+len(extra_cases)} PASS")
    return 0 if n_ok == len(cases) + len(extra_cases) else 1

if __name__ == "__main__":
    sys.exit(main())
