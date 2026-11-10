#!/usr/bin/env python3
"""analyze763b.py — exp763 attempt-2: count-traffic + interval-coverage diagnosis.

Preregistered: PREREG-763-ATTEMPT2.md (sha frozen in FREEZE-763B.txt pre-run).
Fixes attempt-1 void causes: bytes=0 (traffic via dispatch COUNTS under expert-size
homogeneity) and non-compositional shares (overlap-aware interval-union coverage).
Exit 0 DIAGNOSIS-<label> | 3 INCONCLUSIVE | 4 DATA-FAIL | 9 IDENTIFY-FAIL.
Immutable after freeze; re-adjudication requires preregistered settlement + review.
"""
import hashlib, json, os, sys

STAGES = ["expert_dispatch", "expert_completion_handoff", "sync_wait", "routing", "gpu_route_fallback"]
ARMS = ["LGC", "SPEC", "OVR", "ENF"]

def fail(code, msg):
    print(msg); sys.exit(code)

def union_seconds(intervals):
    """Merge [start_ns, start_ns+dur_ns]; return covered seconds."""
    if not intervals:
        return 0.0
    iv = sorted(intervals)
    tot, cs, ce = 0, iv[0][0], iv[0][1]
    for s, e in iv[1:]:
        if s > ce:
            tot += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)
    tot += ce - cs
    return tot / 1e9

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "out"
    man = {}
    for line in open(os.path.join(d, "IO-TRACES-SHA256.txt")):
        h, n = line.split()
        man[n] = h
    agg = {}
    for a in ARMS:
        for i in (1, 2, 3):
            cid = f"{a}_{i}"
            fn = f"{cid}.io.jsonl"
            h = hashlib.sha256(open(os.path.join(d, fn), "rb").read()).hexdigest()
            if man.get(fn) != h:
                fail(9, f"IDENTIFY-FAIL: {fn} sha {h[:12]} != manifest")
            jp = os.path.join(d, f"{cid}.json")
            if not os.path.exists(jp):
                fail(4, f"DATA-FAIL: missing {cid}.json")
            j = json.load(open(jp))
            wall_s = 0.0
            for r in j.get("rows", []):
                if not r.get("decode_tok_s") or not r.get("n_new"):
                    fail(4, f"DATA-FAIL: {cid}.json row missing fields")
                wall_s += r["n_new"] / r["decode_tok_s"]
            ivs = {s: [] for s in STAGES}
            N = {s: 0 for s in STAGES}
            for line in open(os.path.join(d, fn)):
                try:
                    e = json.loads(line)
                except Exception:
                    fail(4, f"DATA-FAIL: malformed line in {cid}")
                s = e.get("stage")
                if s not in ivs:
                    fail(4, f"DATA-FAIL: unexpected stage {s!r} in {cid}")
                ts, du = e.get("ts_ns", 0), e.get("dur_ns", 0)
                if ts is None or du is None or du < 0:
                    fail(4, f"DATA-FAIL: bad ts/dur in {cid}")
                ivs[s].append((ts, ts + du))
                N[s] += 1
            cov = {s: union_seconds(ivs[s]) for s in STAGES}
            unattrib = wall_s - union_seconds([iv for l in ivs.values() for iv in l])
            agg[cid] = {"wall_s": wall_s, "N": N, "cov": cov, "unattrib": unattrib}

    def med(x):
        v = sorted(x); n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    cr, dsync, dhoff, dun, tau, hstars = [], [], [], [], [], []
    for i in (1, 2, 3):
        L, S = agg[f"LGC_{i}"], agg[f"SPEC_{i}"]
        nl, ns = L["N"]["expert_dispatch"], S["N"]["expert_dispatch"]
        cr.append(ns / nl if nl else float("inf"))
        hstars.append(1.0 - nl / ns if ns > nl else 0.0)
        t = 0.05 * L["wall_s"]
        tau.append(t)
        dsync.append(S["cov"]["sync_wait"] - L["cov"]["sync_wait"])
        dhoff.append(S["cov"]["expert_completion_handoff"] - L["cov"]["expert_completion_handoff"])
        dun.append(S["unattrib"] - L["unattrib"])
    m_cr, m_sync, m_hoff, m_un, m_tau = med(cr), med(dsync), med(dhoff), med(dun), med(tau)

    d1 = m_cr >= 1.15 and m_sync <= m_tau and m_un <= m_tau
    d2 = m_sync > m_tau and m_cr < 1.15 and m_un <= m_tau
    d3 = m_hoff > m_tau and not (d1 or d2) and m_un <= m_tau
    d4 = m_un > m_tau and m_cr < 1.15
    mixed = m_cr >= 1.15 and (m_sync > m_tau or m_un > m_tau)
    if mixed: label = "MIXED(policy+scheduling)"
    elif d1: label = "D1-OVER-FETCH-DOMINATED"
    elif d2: label = "D2-STALL-DOMINATED"
    elif d3: label = "D3-HANDOFF-DOMINATED"
    elif d4: label = "D4-POLICY-CPU-DOMINATED"
    else: label = None

    for a in ARMS:
        for i in (1, 2, 3):
            c = agg[f"{a}_{i}"]
            print(f"{a}_{i}: wall={c['wall_s']:.2f}s N_disp={c['N']['expert_dispatch']} "
                  f"cov(sync)={c['cov']['sync_wait']:.2f} cov(handoff)={c['cov']['expert_completion_handoff']:.2f} "
                  f"cov(disp)={c['cov']['expert_dispatch']:.2f} unattrib={c['unattrib']:.2f}s")
    print(f"\nCONTRAST SPEC-vs-LGC: count_ratio med={m_cr:.3f} Δcov_sync={m_sync:+.2f}s "
          f"Δcov_handoff={m_hoff:+.2f}s Δunattrib={m_un:+.2f}s (tau={m_tau:.2f}s)")
    print(f"BREAK-EVEN traffic h* = 1 - N_LGC/N_SPEC (necessary condition): "
          f"med {med(hstars):.3f} [{min(hstars):.3f},{max(hstars):.3f}]")
    for i in (1, 2, 3):
        S_, V = agg[f"SPEC_{i}"], agg[f"OVR_{i}"]
        print(f"OVR-recovery cell{i}: Δcov_sync {V['cov']['sync_wait']-S_['cov']['sync_wait']:+.2f}s "
              f"Δunattrib {V['unattrib']-S_['unattrib']:+.2f}s ΔN_disp {V['N']['expert_dispatch']-S_['N']['expert_dispatch']:+d}")
    print("FOLLOW-UP: D1->prefetch-policy-break-even D2->scheduling D3->exec-path D4->exec-path(policy CPU)")
    if not label:
        fail(3, "VERDICT: INCONCLUSIVE (no preregistered branch armed)")
    print(f"VERDICT: DIAGNOSIS-{label}")
    sys.exit(0)

if __name__ == "__main__":
    main()
