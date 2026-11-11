#!/usr/bin/env python3
"""fixtures776b.py — battery for analyze776b.py."""
import hashlib, json, os, random, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze776b.py")
U, PER, POS, STEPS = 64, 15, 15, 400  # 6000 calls
K = 2

def gen(persist, seed=11):
    """Period-15 calls: position r's expert repeats from its previous step
    with prob `persist`, else uniform over other experts. Adjacent (cross-
    position) overlap stays ~random."""
    rnd = random.Random(seed)
    cur = {r: rnd.randrange(U) for r in range(PER)}
    seq = []
    for s in range(STEPS):
        for r in range(PER):
            if rnd.random() < persist:
                e = cur[r]
            else:
                e = rnd.choice([x for x in range(U) if x != cur[r]])
                cur[r] = e
            l = [e] + rnd.sample([x for x in range(U) if x != e], K - 1)
            seq.append((r, e, l))
    return seq

def write(d, seq):
    lines, ts, t = [], 1000.0, 0
    for i, (r, e, l) in enumerate(seq):
        if i and i % (PER * 32) == 0:
            ts += 2.0
        ts += 0.01
        lines.append(json.dumps({"t": i, "ts": ts, "topk": l, "routed": [e]}))
    open(os.path.join(d, "out", "PY_DBL.rl.jsonl"), "w").write("\n".join(lines) + "\n")

def build():
    d = tempfile.mkdtemp(prefix="f776b-")
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    return d

def run(d, expect=""):
    r = subprocess.run([sys.executable, AN, d, d, expect], capture_output=True, text=True)
    rc = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="):
            rc = int(ln[3:])
    return rc, r.stdout + r.stderr

def sha16f(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]

def main():
    global STEPS
    n_ok = total = 0
    cases = [
        # name, expect_rc, grep, persist, steps
        ("reopened", 1, "REOPENED", 0.55, STEPS),
        ("weak-memory", 2, "WEAK-MEMORY", 0.17, STEPS),
        ("confirmed", 7, "CONFIRMED", 0.02, STEPS),
        ("short-logs", 4, "DATA-FAIL", 0.17, 60),  # 900 calls -> 885 pairs < 2000
    ]
    for name, expect, grep, persist, steps in cases:
        _sv, STEPS = STEPS, steps
        d = build(); write(d, gen(persist)); STEPS = _sv
        sh = sha16f(os.path.join(d, "out", "PY_DBL.rl.jsonl"))
        rc, out = run(d, sh)
        ok = rc == expect and grep in out
        n_ok += ok; total += 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok: print(out[-500:])
        shutil.rmtree(d, ignore_errors=True)
    # identify: wrong expected sha
    d = build(); write(d, gen(0.17))
    rc, out = run(d, "deadbeefdeadbeef")
    ok = rc == 9 and "IDENTIFY-FAIL" in out
    n_ok += ok; total += 1
    print(f"{'PASS' if ok else 'FAIL'} identify: expect rc=9 got rc={rc}")
    shutil.rmtree(d, ignore_errors=True)
    # non-period-15 input
    d = build()
    lines = [json.dumps({"t": i, "ts": 1000 + i * 0.01, "topk": [1, 2], "routed": [3]}) for i in range(1001)]
    open(os.path.join(d, "out", "PY_DBL.rl.jsonl"), "w").write("\n".join(lines) + "\n")
    rc, out = run(d, "")
    ok = rc == 9 and "IDENTIFY-FAIL" in out
    n_ok += ok; total += 1
    print(f"{'PASS' if ok else 'FAIL'} non-periodic: expect rc=9 got rc={rc}")
    shutil.rmtree(d, ignore_errors=True)
    print(f"\n{n_ok}/{total} PASS")
    return 0 if n_ok == total else 1

if __name__ == "__main__":
    sys.exit(main())
