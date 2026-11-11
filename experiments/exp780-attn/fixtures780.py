#!/usr/bin/env python3
"""exp780 fixtures: synthetic run dirs for every analyzer rc branch. 10 cases."""
import json, os, shutil, subprocess, sys, tempfile

ANA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze780.py")

def mkrow(t1, tf, n=64, sha="a" * 16):
    return {"i": 0, "n_in": 40, "n_new": n, "t_1tok_s": t1, "t_full_s": tf, "win_full": [0, 0],
            "decode_tok_s": (n - 1) / max(tf - t1, 1e-9), "out_sha": sha, "out_ids": [1] * n,
            "stats_delta": {}, "routing_delta": {}}

def build(base, ws_rows, we_rows=None, *, cell="both", sha="3571f714c811e1c7", engb="deadbeefdeadbeef",
          rcS=0, rcE=0, badio="", banner="", implS=("sdpa", True), implE=("eager", True),
          src="b7f6ca4cafecafecafecafecafecafe",
          env="moei-RC753 /x\nmoei-776 /home/mfeth/exp776/src776/moe_infinity/__init__.py\nflash_attn: ABSENT"):
    d = tempfile.mkdtemp(prefix="fx780_", dir=base)
    os.makedirs(f"{d}/out")
    open(f"{d}/out/SRC_HEAD.txt", "w").write(src)
    open(f"{d}/out/ENV.txt", "w").write(env)
    open(f"{d}/out/SRC776_FILE_SHA.txt", "w").write(sha)
    open(f"{d}/out/ENGB_SHA.txt", "w").write(engb)
    open(f"{d}/out/CELL_RC.txt", "w").write(f"PY_SDPA RC={rcS}\nPY_EAGER RC={rcE}\n")
    if badio:
        open(f"{d}/out/BADIO", "w").write(badio)
    if banner:
        open(f"{d}/out/BANNER-FAIL", "w").write(banner)
    def dump(cid, impl, rows):
        j = {"arm": "780-attn", "attn_impl": impl[0], "attn_ok": impl[1],
             "attn_default": ["sdpa"], "attn_effective": [impl[0]] if impl[1] else ["sdpa"],
             "attn_nmod": 16, "rows": [dict(r) for r in rows]}
        for i, r in enumerate(j["rows"]):
            r["out_sha"] = f"{i:016x}" if i % 3 else f"{i:015x}f"
        open(f"{d}/out/{cid}.json", "w").write(json.dumps(j))
    if ws_rows is not None:
        dump("PY_SDPA", implS, ws_rows)
    if we_rows is not None:
        dump("PY_EAGER", implE, we_rows)
    return d

def run(base, name, d, want):
    vd = tempfile.mkdtemp(prefix="vd780_", dir=base)
    r = subprocess.run([sys.executable, ANA, d, vd], capture_output=True, text=True)
    got = r.returncode
    v = open(f"{vd}/verdict780.txt", errors="replace").read() if os.path.exists(f"{vd}/verdict780.txt") else ""
    shutil.rmtree(d); shutil.rmtree(vd)
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'} {name}: rc={got} want={want}")
    if not ok:
        print(r.stdout[-400:], r.stderr[-400:], v[-300:])
    return ok

def main():
    base = tempfile.mkdtemp(prefix="fx780_base_")
    res = []
    # manual-loop ref 190; sdpa row 7.5*24=180 inside gate
    S = [mkrow(0.3, 7.2) for _ in range(24)]   # W_sdpa=180
    E = [mkrow(0.3, 8.0) for _ in range(24)]   # W_eager=198.9? 8.3*24=199.2
    # compute: gain=(We-Ws)/We with Ws=180, We=199.2 -> 0.0964 ~ MILD edge; adjust below per case
    res.append(run(base, "kernel-matters rc1", build(base, S, [mkrow(0.3, 8.3) for _ in range(24)]), 1))      # We=199.2 -> .0964? recompute in build; use 8.4 -> 8.7*24=208.8 -> gain .1378
    res.append(run(base, "mild rc2", build(base, S, [mkrow(0.3, 7.65) for _ in range(24)]), 2))               # We=7.95*24=190.8 gain .0566
    res.append(run(base, "no-kernel-gain rc7", build(base, S, [mkrow(0.3, 7.25) for _ in range(24)]), 7))     # We=7.55*24=181.2 gain .0066
    res.append(run(base, "sdpa-regression rc3", build(base, S, [mkrow(0.3, 6.9) for _ in range(24)]), 3))     # We=7.2*24=172.8 gain -.0409
    res.append(run(base, "sdpa-regression-large rc5", build(base, S, [mkrow(0.3, 6.3) for _ in range(24)]), 5))  # We=6.6*24=158.4 gain -.1364
    res.append(run(base, "identify-fail sha rc9", build(base, S, [mkrow(0.3, 8.4) for _ in range(24)], sha="ffffffffffffffff"), 9))
    res.append(run(base, "banner-fail rc9", build(base, S, [mkrow(0.3, 8.4) for _ in range(24)], banner="PY_SDPA impl-banner-bad"), 9))
    res.append(run(base, "impl-unverified rc4", build(base, S, [mkrow(0.3, 8.4) for _ in range(24)], implE=("eager", False)), 4))
    res.append(run(base, "covariate-fail rc4", build(base, [mkrow(0.2, 4.6) for _ in range(24)], [mkrow(0.3, 8.4) for _ in range(24)]), 4))  # Ws=4.9*24=117.6 <142.5
    res.append(run(base, "eager-missing rc4", build(base, S, None, rcE=3), 4))
    shutil.rmtree(base)
    n = sum(res)
    print(f"{n}/{len(res)}")
    return 0 if n == len(res) else 1

if __name__ == "__main__":
    sys.exit(main())
