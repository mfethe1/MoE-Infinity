#!/usr/bin/env python3
"""exp781 analyzer: async-dbuf (EXP773_DB=1) vs blocking topk (unset).

delta = (W_block - W_adbuf) / W_block ; positive = async double-buffer saves wall.
rc 1 OVERLAP-MATTERS >= 0.15 ; 2 MILD [0.05, 0.15) ; 7 NO-MOVE < 0.05 ;
   3 ADBUF-REGRESSION <= -0.03 ; 5 LARGE-REGRESSION <= -0.10 ; 9 DATA-FAIL.
Covariate: W(adbuf) in [142.50, 237.50] (exp779/780 manual-loop refs 190.00/184.93 +/-25%).
Identify gates: SRC_HEAD b7f6ca4*, ENV moei-776 path, prefetcher sha 3571f714c811e1c7,
ENGB non-empty, per-cell banner db flag, env_db JSON field, CELL_RC 0, n_new=64.
Report-only: out_sha agreement, tok/s, io.jsonl stage-duration side-check.
"""
import json, os, sys, glob


def loadW(d, cid, db):
    p = os.path.join(d, "out", cid + ".json")
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        return None, None
    res = json.load(open(p))
    rr = res.get("rows") or []
    if len(rr) < 20 or res.get("env_db") != db:
        return None, res
    W = sum(r["t_1tok_s"] + r["t_full_s"] for r in rr)
    return W, res


def io_stages(d, cid):
    p = os.path.join(d, "out", cid + ".io.jsonl")
    out = {}
    if not os.path.exists(p):
        return out
    import collections
    dur = collections.defaultdict(float)
    with open(p) as f:
        for ln in f:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            dur[e.get("stage", "?")] += e.get("dur_ns", 0) / 1e9
    for k in ("sync_wait", "expert_completion_handoff", "expert_dispatch", "gpu_route_fallback"):
        if k in dur:
            out[k] = round(dur[k], 2)
    return out


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    out = os.path.join(d, "out")

    def rd(n):
        p = os.path.join(out, n)
        return open(p, errors="replace").read().strip() if os.path.exists(p) else ""
    src = rd("SRC_HEAD.txt"); env = rd("ENV.txt"); sha = rd("SRC776_FILE_SHA.txt"); engb = rd("ENGB_SHA.txt")
    badio = rd("BADIO"); banner = rd("BANNER-FAIL")
    rcs = {}
    for ln in rd("CELL_RC.txt").splitlines():
        parts = ln.split()
        if len(parts) >= 2 and "RC=" in ln:
            rcpart = [q for q in parts if q.startswith("RC=")][0]
            rcs[parts[0]] = int(rcpart[3:])
    def loghas(cid, needle):
        p = os.path.join(out, cid + ".log")
        try:
            return needle in open(p, errors="replace").read()
        except FileNotFoundError:
            return False
    L = ["exp781 async-dbuf vs blocking topk wall test (manual-loop decode)"]

    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict781.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    if not src.startswith("b7f6ca4") or "moei-776 /home/mfeth/exp776/src776" not in env \
            or sha != "3571f714c811e1c7" or not engb:
        L.append(f"IDENTIFY-FAIL (src={src[:12]!r} sha={sha!r} engb={engb!r})"); return fin(9)
    if banner:
        L.append(f"IDENTIFY-FAIL banner: {banner[:80]}"); return fin(9)
    if badio:
        L.append(f"DATA-FAIL BADIO non-empty: {badio[:80]}"); return fin(4)
    if rcs.get("PY_ADBUF") != 0 or rcs.get("PY_BLOCK") != 0:
        L.append(f"DATA-FAIL cell RC: {rcs}"); return fin(9)
    if not loghas("PY_ADBUF", "exp781 db=1 ok=True") or not loghas("PY_BLOCK", "exp781 db=0 ok=True"):
        L.append("DATA-FAIL banner db-flag mismatch"); return fin(9)
    Wa, ra = loadW(d, "PY_ADBUF", "1")
    Wb, rb = loadW(d, "PY_BLOCK", "0")
    if Wa is None or Wb is None:
        L.append(f"DATA-FAIL load (Wa={Wa} Wb={Wb})"); return fin(9)
    for nm, res in (("adbuf", ra), ("block", rb)):
        nn = [r.get("n_new") for r in (res.get("rows") or [])]
        if any(x != 64 for x in nn):
            L.append(f"DATA-FAIL n_new!=64 in {nm}: {sorted(set(nn))}"); return fin(9)
    L.append(f"PY_ADBUF  W={Wa:.2f} env_db=1")
    L.append(f"PY_BLOCK  W={Wb:.2f} env_db=0")
    if not (142.50 <= Wa <= 237.50):
        L.append(f"COVFAIL W(adbuf)={Wa:.2f} outside [142.50, 237.50]"); return fin(9)
    delta = (Wb - Wa) / Wb
    L.append(f"covariate: W(adbuf)={Wa:.2f} vs gate [142.50, 237.50] (exp779/780 manual-loop refs)")
    L.append(f"delta = (W_block - W_adbuf)/W_block = {delta:+.4f}")
    sh_a = [r.get("out_sha") for r in ra["rows"]]; sh_b = [r.get("out_sha") for r in rb["rows"]]
    agree = sum(1 for x, y in zip(sh_a, sh_b) if x == y)
    L.append(f"out_sha agreement adbuf/block: {agree}/{len(sh_a)} (report-only)")
    tks_a = sum(r.get("n_new", 64) for r in ra["rows"]) / Wa * 1.0
    tks_b = sum(r.get("n_new", 64) for r in rb["rows"]) / Wb * 1.0
    L.append(f"tok/s adbuf={tks_a:.3f} block={tks_b:.3f}")
    ioa, iob = io_stages(d, "PY_ADBUF"), io_stages(d, "PY_BLOCK")
    if ioa or iob:
        L.append(f"io side-check (report-only): adbuf={ioa} block={iob}")
    if delta >= 0.15:
        L.append("OVERLAP-MATTERS: async double-buffering cuts wall >= 15%"); rc = 1
    elif delta >= 0.05:
        L.append("MILD: async double-buffering saves 5-15% wall"); rc = 2
    elif delta <= -0.10:
        L.append("LARGE-REGRESSION: async double-buffering costs > 10% wall"); rc = 5
    elif delta <= -0.03:
        L.append("ADBUF-REGRESSION: async double-buffering costs 3-10% wall"); rc = 3
    else:
        L.append("NO-MOVE: topk D2H overlap does not move batch-1 decode wall (<5%)"); rc = 7
    return fin(rc)


if __name__ == "__main__":
    sys.exit(main())
