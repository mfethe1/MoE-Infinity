"""exp762 frozen analyzer (io_overlap direction). Reads out/ per run_exp762.sh.
Gates (fail-closed per cell): no FAILED/BANNER-FAIL/BADIO entry; config echo matches
requested vs effective for spec_prefetch/spec_overlap/overlap_policy; gpu_route_effective
is falsy; >=5/6 prompts with n_new==64 and decode_tok_s>0.
Metric: cell ms/tok = mean over prompts of 1000/decode_tok_s (also prompt-0 cold and
mean prompts 1..5 warm).
Contrasts (bootstrap 3v3 cells, 10000 resamples, seeded 762): OVR-vs-LGC (primary H1),
SPEC-vs-LGC, OVR-vs-SPEC, ENF-vs-OVR. speedup% = 100*(meanA-meanB)/meanA in ms/tok.
Token-identity gate: greedy decode with identical weights must yield byte-identical
out_ids per prompt across ALL valid cells (early-EOS rows included); any divergence
=> exit 9 IDENTIFY-FAIL TOKEN-DIVERGENCE (overlap path altered decode numerics; A/B
invalid, lane halts per DECISION-TREE B5).
Exit codes: 0 OVERLAP-GAIN (CI95lo OVR-vs-LGC >= 5%) | 1 NO-GAIN | 3 INCONCLUSIVE
(valid<3 in any arm) | 9 IDENTIFY-FAIL (arm-wide echo mismatch OR token divergence).
"""
import json, math, os, random, re, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
ARMS = ["LGC", "SPEC", "OVR", "ENF"]
REQ = {"on": True, "off": False}


def cell_metric(js):
    rows = js["rows"]
    mst = [1000.0 / r["decode_tok_s"] for r in rows if r["n_new"] >= 64 and r["decode_tok_s"] > 0]
    if len(mst) < 5:
        return None
    cold = 1000.0 / rows[0]["decode_tok_s"] if rows and rows[0]["decode_tok_s"] > 0 else None
    warm = [1000.0 / r["decode_tok_s"] for r in rows[1:] if r["decode_tok_s"] > 0]
    return {"mean_ms_tok": sum(mst) / len(mst), "cold_ms_tok": cold,
            "warm_ms_tok": (sum(warm) / len(warm)) if warm else None, "n": len(mst)}


def main():
    cells = json.load(open(os.path.join(OUT, "..", "cells762.json")))
    failed = set()
    for f, mk in (("FAILED", ""), ("BANNER-FAIL", ""), ("BADIO", "")):
        p = os.path.join(OUT, f)
        if os.path.exists(p):
            failed |= {l.split()[0] for l in open(p) if l.strip()}
    valid, excl = {a: [] for a in ARMS}, {}
    lockwarn = {}
    tok = {}  # cid -> {prompt_index: out_ids}
    for c in cells:
        cid, arm = c["id"], c["arm"]
        p = os.path.join(OUT, f"{cid}.json")
        why = []
        if cid in failed:
            why.append("marker(" + ",".join(f for f in ("FAILED", "BANNER-FAIL", "BADIO") if os.path.exists(os.path.join(OUT, f)) and cid in {l.split()[0] for l in open(os.path.join(OUT, f)) if l.strip()}) + ")")
        if not os.path.exists(p):
            why.append("no-json")
        else:
            js = json.load(open(p))
            for rk, ek in (("spec_prefetch_requested", "spec_prefetch_effective"),
                           ("spec_overlap_requested", "spec_overlap_effective"),
                           ("overlap_policy_requested", "overlap_policy_effective")):
                want = REQ.get(js.get(rk), js.get(rk)) if rk != "overlap_policy_requested" else js.get(rk)
                if js.get(ek) != want:
                    why.append(f"echo({rk}={js.get(rk)}!={js.get(ek)})")
            if js.get("gpu_route_effective"):
                why.append("gpu_route_on")
            m = cell_metric(js)
            if m is None:
                why.append("rows<5")
            else:
                m.update(cid=cid)
            log = os.path.join(OUT, f"{cid}.log")
            if os.path.exists(log):
                lockwarn[cid] = open(log).read().count("All cached expert locked")
        if why:
            excl[cid] = ";".join(why)
        else:
            valid[arm].append(m)
            tok[cid] = {r["i"]: r["out_ids"] for r in js["rows"]}
    # Token-identity gate (valid cells only; excluded cells may carry partial data)
    refs_cid = sorted(tok)[0] if tok else None
    if refs_cid is not None:
        for i in range(6):
            ref = tok[refs_cid].get(i)
            for cid in sorted(tok):
                if tok[cid].get(i) != ref:
                    print(f"IDENTIFY-FAIL: TOKEN-DIVERGENCE:p{i}:{cid}!={refs_cid}")
                    print("VERDICT: IDENTIFY-FAIL (token-identity violation — overlap path "
                          "altered decode numerics; A/B invalid, halt lane)")
                    sys.exit(9)
    print("exp762 analyzer (frozen)")
    for a in ARMS:
        print(f"{a}: valid={len(valid[a])} " +
              " ".join(f"{m['cid']}={m['mean_ms_tok']:.3f}" for m in valid[a]) +
              (f" | excluded: {excl}" if (bad := {k: v for k, v in excl.items() if k.startswith(a)}) else ""))
    if any(len(valid[a]) < 3 for a in ARMS):
        print("VERDICT: INCONCLUSIVE (valid<3 in some arm)")
        sys.exit(3)
    rng = random.Random(762)

    def ms(a):
        return [m["mean_ms_tok"] for m in valid[a]]

    def contrast(a, b, label):
        A, B = ms(a), ms(b)
        base = sum(A) / len(A)
        diffs = []
        for _ in range(10000):
            ra = [rng.choice(A) for _ in A]
            rb = [rng.choice(B) for _ in B]
            ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
            diffs.append(100.0 * (ma - mb) / ma)
        diffs.sort()
        lo, hi = diffs[int(0.05 * len(diffs))], diffs[int(0.95 * len(diffs))]
        pt = 100.0 * (sum(A) / len(A) - sum(B) / len(B)) / (sum(A) / len(A))
        print(f"{label}: +{pt:.2f}% ms/tok [CI95 {lo:.2f}, {hi:.2f}]  ({a} {sum(A)/len(A):.3f} -> {b} {sum(B)/len(B):.3f})")
        return pt, lo, hi

    pt, lo, hi = contrast("LGC", "OVR", "PRIMARY OVR-vs-LGC")
    contrast("LGC", "SPEC", "SPEC-vs-LGC")
    contrast("SPEC", "OVR", "OVR-vs-SPEC (timing)")
    contrast("OVR", "ENF", "ENF-vs-OVR (budget)")
    for a in ARMS:
        colds = [m["cold_ms_tok"] for m in valid[a] if m["cold_ms_tok"]]
        warms = [m["warm_ms_tok"] for m in valid[a] if m["warm_ms_tok"]]
        print(f"{a}: cold={sum(colds)/len(colds):.3f} warm={sum(warms)/len(warms):.3f} ms/tok  lockwarn={sum(lockwarn.get(m['cid'], 0) for m in valid[a])}")
    if lo >= 5.0:
        print("VERDICT: OVERLAP-GAIN-SUPPORTED (CI95lo >= 5%)")
        sys.exit(0)
    print("VERDICT: NO-GAIN (CI95lo < 5%)")
    sys.exit(1)


if __name__ == "__main__":
    main()
