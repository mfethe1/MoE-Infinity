#!/usr/bin/env python3
"""fixtures776.py — battery for analyze776.py."""
import json, os, random, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze776.py")
ENVLINE = "moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py\nmoei-776 /home/mfeth/exp776/src776/moe_infinity/__init__.py\ntorch 2.x\n"
U, RS = 64, 12  # universe, routed-set size
K = 2

def gen(n, keep_frac, heur_in_next, seed):
    """Routed sets keep ceil(keep_frac*RS) of previous; topk list overlaps
    next routed set in heur_in_next elements (0..K)."""
    rnd = random.Random(seed)
    r = rnd.sample(range(U), RS)
    seq = []
    for i in range(n):
        nxt = rnd.sample(sorted(r), int(round(keep_frac * RS)))
        pool = [x for x in range(U) if x not in r]
        nxt += rnd.sample(pool, RS - len(nxt))
        nxt_set = set(nxt)
        # heuristic list for THIS call: heur_in_next of NEXT routed + fill
        l = rnd.sample(sorted(nxt_set), min(heur_in_next, K))
        l += rnd.sample([x for x in range(U) if x not in nxt_set], K - len(l))
        seq.append((r, l))
        r = nxt_set
    return seq

def write(d, seq):
    ts, t, lines = 1000.0, 0.0, []
    for i, (r, l) in enumerate(seq):
        if i and i % 64 == 0:
            t += 2.0
        t += 0.05
        lines.append(json.dumps({"t": i, "ts": ts + t, "topk": l, "routed": sorted(r)}))
    open(os.path.join(d, "out", "PY_DBL.rl.jsonl"), "w").write("\n".join(lines) + "\n")

def build(src="b7f6ca4d2caa5229698d78deb03b454fc20947dd", env=ENVLINE, badio=""):
    d = tempfile.mkdtemp(prefix="f776-")
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    open(os.path.join(d, "out", "SRC_HEAD.txt"), "w").write(src + "\n")
    open(os.path.join(d, "out", "ENV.txt"), "w").write(env)
    open(os.path.join(d, "out", "BADIO"), "w").write(badio)
    rows = [{"t_1tok_s": 0.5, "t_full_s": 7.4} for _ in range(24)]
    json.dump({"rows": rows}, open(os.path.join(d, "out", "PY_DBL.json"), "w"))
    return d

def run(d):
    r = subprocess.run([sys.executable, AN, d, d], capture_output=True, text=True)
    rc = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="):
            rc = int(ln[3:])
    return rc, r.stdout + r.stderr

# keep_frac -> persistence approx; heur_in_next -> H approx heur/RS
# ceiling k/|R| = 2/12 = 0.167
CASES = [
    # name, expect_rc, grep, keep_frac, heur_in_next, n
    ("predictive-lift", 1, "PREDICTIVE-LIFT", 0.75, 0, 1600),   # P~.75 H~0 lift .75
    ("lift-only-fails-persist", 2, "MILD-LIFT", 0.35, 0, 1600),  # lift .35>=.15 but P .35<.40
    ("mild", 2, "MILD-LIFT", 0.30, 2, 1600),                    # P~.30 H~.167 lift .133 in [.05,.15)
    ("no-lift", 7, "NO-LIFT", 0.18, 2, 1600),                   # lift ~.013
    ("short-logs", 4, "DATA-FAIL", 0.75, 0, 80),                # pairs < 200
]

def main():
    n_ok = total = 0
    for name, expect, grep, kf, hi, n in CASES:
        d = build()
        write(d, gen(n, kf, hi, seed=7))
        rc, out = run(d)
        ok = rc == expect and grep in out
        n_ok += ok; total += 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not ok:
            print(out[-600:])
        shutil.rmtree(d, ignore_errors=True)
    for name, expect, grep, kw in [
        ("identify-fail", 9, "IDENTIFY-FAIL", dict(src="deadbeef")),
        ("env-fail", 9, "IDENTIFY-FAIL", dict(env="moei-RC753 only\n")),
        ("badio-fail", 4, "DATA-FAIL", dict(badio="PY_DBL rl-empty\n")),
    ]:
        d = build(**kw)
        write(d, gen(1600, 0.75, 0, seed=7))
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
