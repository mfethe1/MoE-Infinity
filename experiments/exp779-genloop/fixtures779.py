#!/usr/bin/env python3
"""exp779 fixtures: synthetic run dirs for every analyzer rc branch. 9 cases."""
import json, os, shutil, subprocess, sys, tempfile

ANA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze779.py")

def mkrow(t1, tf, n=64, sha="a" * 16):
    return {"i": 0, "n_in": 40, "n_new": n, "t_1tok_s": t1, "t_full_s": tf, "win_full": [0, 0],
            "decode_tok_s": (n - 1) / max(tf - t1, 1e-9), "out_sha": sha, "out_ids": [1] * n,
            "stats_delta": {}, "routing_delta": {}}

def build(base, wa_rows, wb_rows=None, *, sha="3571f714c811e1c7", engb="deadbeefdeadbeef",
          rcA=0, rcB=0, badio="", armB="B-manual-dynamic", src="b7f6ca4cafecafecafecafecafecafe",
          env="moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py torch 2.11.0+cu128\nmoei-776 /home/mfeth/exp776/src776/moe_infinity/__init__.py"):
    d = tempfile.mkdtemp(prefix="fx779_", dir=base)
    os.makedirs(f"{d}/out")
    open(f"{d}/out/SRC_HEAD.txt", "w").write(src)
    open(f"{d}/out/ENV.txt", "w").write(env)
    open(f"{d}/out/SRC776_FILE_SHA.txt", "w").write(sha)
    open(f"{d}/out/ENGB_SHA.txt", "w").write(engb)
    open(f"{d}/out/CELL_RC.txt", "w").write(f"PY_A RC={rcA}\nPY_B RC={rcB}\n")
    if badio:
        open(f"{d}/out/BADIO", "w").write(badio)
    ja = {"arm": "A-generate", "rows": [dict(r) for r in wa_rows]}
    for i, r in enumerate(ja["rows"]):
        r["out_sha"] = f"{i:016x}"
    open(f"{d}/out/PY_A.json", "w").write(json.dumps(ja))
    if wb_rows is not None:
        jb = {"arm": armB, "rows": [dict(r) for r in wb_rows]}
        for i, r in enumerate(jb["rows"]):
            r["out_sha"] = f"{i:016x}" if i % 3 else f"{i:015x}f"
        open(f"{d}/out/PY_B.json", "w").write(json.dumps(jb))
    return d

def run(base, name, d, want):
    vd = tempfile.mkdtemp(prefix="vd779_", dir=base)
    r = subprocess.run([sys.executable, ANA, d, vd], capture_output=True, text=True)
    got = r.returncode
    v = open(f"{vd}/verdict779.txt", errors="replace").read() if os.path.exists(f"{vd}/verdict779.txt") else ""
    shutil.rmtree(d); shutil.rmtree(vd)
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'} {name}: rc={got} want={want}")
    if not ok:
        print(r.stdout[-400:], r.stderr[-400:], v[-300:])
    return ok

def main():
    base = tempfile.mkdtemp(prefix="fx779_base_")
    res = []
    # 24 rows of 2.5s -> Wa=180 inside gate
    A = [mkrow(0.3, 7.2) for _ in range(24)]
    res.append(run(base, "large-move rc1", build(base, A, [mkrow(0.3, 5.5) for _ in range(24)]), 1))
    res.append(run(base, "mild-move rc2", build(base, A, [mkrow(0.3, 6.55) for _ in range(24)]), 2))
    res.append(run(base, "no-move rc7", build(base, A, [mkrow(0.3, 7.16) for _ in range(24)]), 7))
    res.append(run(base, "identify-fail rc9", build(base, A, [mkrow(0.3, 5.5) for _ in range(24)], sha="ffffffffffffffff"), 9))
    res.append(run(base, "covariate-fail rc4", build(base, [mkrow(0.2, 3.9) for _ in range(24)], [mkrow(0.3, 5.5) for _ in range(24)]), 4))
    res.append(run(base, "B-missing rc4", build(base, A, None, rcB=3), 4))
    res.append(run(base, "BADIO rc4", build(base, A, [mkrow(0.3, 5.5) for _ in range(24)], badio="PY_A oscsv-empty RC=0"), 4))
    res.append(run(base, "arm-wrong rc9", build(base, A, [mkrow(0.3, 5.5) for _ in range(24)], armB="A-generate"), 9))
    res.append(run(base, "B-nnew-wrong rc4", build(base, A, [mkrow(0.3, 5.5, n=63) for _ in range(24)]), 4))
    shutil.rmtree(base)
    n = sum(res)
    print(f"{n}/{len(res)}")
    return 0 if n == len(res) else 1

if __name__ == "__main__":
    sys.exit(main())
