#!/usr/bin/env python3
"""fixtures775.py — battery for analyze774/775-style dirs; tests analyze775.py."""
import json, os, random, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze775.py")
ENVLINE = "moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py\nmoei-775 /home/mfeth/exp775/src775/moe_infinity/__init__.py\ntorch 2.x\n"
K, U = 10, 26

def gen_lag1(n, m_fn, seed):
    """Sequence whose consecutive overlap m_fn(i) controls hit(i-1,i) exactly."""
    rnd = random.Random(seed)
    prev = rnd.sample(range(U), K)
    seq = [prev]
    for i in range(1, n):
        m = m_fn(i)
        keep = rnd.sample(seq[-1], m)
        pool = [x for x in range(U) if x not in seq[-1]]
        seq.append(keep + rnd.sample(pool, K - m))
    return seq

def gen_lag2(n, m_fn, seed):
    """Sequence whose lag-2 overlap m_fn(i) controls hit(i-2,i) exactly."""
    rnd = random.Random(seed)
    seq = [rnd.sample(range(U), K), rnd.sample(range(U), K)]
    for i in range(2, n):
        m = m_fn(i)
        keep = rnd.sample(seq[i - 2], m)
        pool = [x for x in range(U) if x not in seq[i - 2]]
        seq.append(keep + rnd.sample(pool, K - m))
    return seq

def write_hits(d, arm, seq):
    ts, lines, t = 1000.0, [], 0.0
    key = "issued" if arm == "PY_SPEC" else "consumed"
    for i, lst in enumerate(seq):
        if i and i % 64 == 0:
            t += 2.0  # prompt boundary gap -> pair excluded
        t += 0.05
        lines.append(json.dumps({"t": i, "ts": ts + t, key: lst}))
    open(os.path.join(d, "out", arm + ".hits.jsonl"), "w").write("\n".join(lines) + "\n")

def write_rows(d, arm, W):
    rows = [{"t_1tok_s": 0.5, "t_full_s": (W - 12.0) / 24.0, "decode_tok_s": 9.0} for _ in range(24)]
    json.dump({"rows": rows}, open(os.path.join(d, "out", arm + ".json"), "w"))

def build(src="b7f6ca4d2caa5229698d78deb03b454fc20947dd", env=ENVLINE, badio=""):
    d = tempfile.mkdtemp(prefix="f775-")
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

def alt(a, b):
    return lambda i: a if i % 2 else b

# SPEC always 9/8 -> hit 0.85. DB varies per case. 1600 calls ~ 1500 valid pairs.
CASES = [
    # name, expect_rc, grep, db_m_pair, spec_W, db_W, n_calls
    ("retained", 1, "RETAINED", (9, 8), 212.13, 179.72, 1600),   # D = 0.00
    ("eroded", 2, "ERODED", (8, 8), 212.13, 179.72, 1600),      # D ~ -0.05 mid-band
    ("severe", 7, "SEVERE", (7, 6), 212.13, 179.72, 1600),       # D = -0.20
    ("short-logs", 4, "DATA-FAIL", (9, 8), 212.13, 179.72, 80),  # pairs < 200
    ("wall-dev", 4, "wall deviates", (9, 8), 212.13, 260.0, 1600),  # DB wall +45% vs ref
]

def main():
    n_ok = 0
    total = 0
    for name, expect, grep, dbm, sw, dw, n in CASES:
        d = build()
        write_rows(d, "PY_SPEC", sw)
        write_rows(d, "PY_DB", dw)
        write_hits(d, "PY_SPEC", gen_lag1(n, alt(9, 8), seed=11))
        write_hits(d, "PY_DB", gen_lag2(n, alt(*dbm), seed=22))
        rc, out = run(d)
        ok = rc == expect and grep in out
        n_ok += ok; total += 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok:
            print(out[-700:])
        shutil.rmtree(d, ignore_errors=True)
    for name, expect, grep, kw in [
        ("identify-fail", 9, "IDENTIFY-FAIL", dict(src="deadbeef")),
        ("env-fail", 9, "IDENTIFY-FAIL", dict(env="moei-RC753 only\n")),
        ("badio-fail", 4, "DATA-FAIL", dict(badio="PY_DB hits-empty\n")),
    ]:
        d = build(**kw)
        write_rows(d, "PY_SPEC", 212.13)
        write_rows(d, "PY_DB", 179.72)
        write_hits(d, "PY_SPEC", gen_lag1(1600, alt(9, 8), seed=11))
        write_hits(d, "PY_DB", gen_lag2(1600, alt(9, 8), seed=22))
        rc, out = run(d)
        ok = rc == expect and grep in out
        n_ok += ok; total += 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok:
            print(out[-500:])
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{n_ok}/{total} PASS")
    return 0 if n_ok == total else 1

if __name__ == "__main__":
    sys.exit(main())
