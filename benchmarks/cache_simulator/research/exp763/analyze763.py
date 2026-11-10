#!/usr/bin/env python3
"""analyze763.py — exp763 I/O-trace diagnosis of the spec-prefetch regression.

Preregistered metrics/contrasts/decision tree: PREREG-763.md (sha frozen pre-run).
Reads: <dir>/<cell>.io.jsonl, <dir>/<cell>.json, <dir>/IO-TRACES-SHA256.txt.
Exit 0 DIAGNOSIS-<label> | 3 INCONCLUSIVE | 4 DATA-FAIL | 9 IDENTIFY-FAIL.
Immutable after freeze; re-adjudication requires preregistered settlement rule + review.
"""
import hashlib, json, math, os, re, sys

STAGES = ["expert_dispatch", "expert_completion_handoff", "sync_wait", "routing", "gpu_route_fallback"]
ARMS = ["LGC", "SPEC", "OVR", "ENF"]
CELLS = [f"{a}_{i}" for a in ARMS for i in (1, 2, 3)]

def fail(code, msg):
    print(msg); sys.exit(code)

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "out"
    # ---- identity gate: io traces must match frozen sha manifest ----
    man = {}
    mp = os.path.join(d, "IO-TRACES-SHA256.txt")
    if not os.path.exists(mp):
        fail(4, "DATA-FAIL: missing IO-TRACES-SHA256.txt")
    for line in open(mp):
        h, n = line.split()
        man[n] = h
    for a in ARMS:
        for i in (1, 2, 3):
            cid = f"{a}_{i}"
            fn = f"{cid}.io.jsonl"
            h = hashlib.sha256(open(os.path.join(d, fn), "rb").read()).hexdigest()
            if man.get(fn) != h:
                fail(9, f"IDENTIFY-FAIL: {fn} sha {h[:12]} != manifest {str(man.get(fn))[:12]}")

    # ---- per-cell aggregation ----
    agg = {}
    for cid in CELLS:
        jp = os.path.join(d, f"{cid}.json")
        if not os.path.exists(jp):
            fail(4, f"DATA-FAIL: missing {cid}.json")
        try:
            j = json.load(open(jp))
        except Exception as e:
            fail(4, f"DATA-FAIL: malformed {cid}.json: {e}")
        # wall decode time: sum over rows of n_new / decode_tok_s
        wall_s = 0.0
        for r in j.get("rows", []):
            tok_s = r.get("decode_tok_s")
            n = r.get("n_new")
            if not tok_s or not n:
                fail(4, f"DATA-FAIL: {cid}.json row missing n_new/decode_tok_s")
            wall_s += n / tok_s
        st = {s: [0, 0] for s in STAGES}  # [count, dur_ns]
        B = 0
        nline = 0
        for line in open(os.path.join(d, f"{cid}.io.jsonl")):
            nline += 1
            try:
                e = json.loads(line)
            except Exception:
                fail(4, f"DATA-FAIL: malformed line {nline} in {cid}.io.jsonl")
            s = e.get("stage")
            if s not in st:
                fail(4, f"DATA-FAIL: unexpected stage {s!r} in {cid}")
            st[s][0] += 1
            st[s][1] += e.get("dur_ns", 0)
            if s == "expert_dispatch":
                B += e.get("bytes", 0)
        agg[cid] = {"wall_s": wall_s, "bytes": B, "stages": st}

    def share(cid, s):
        return agg[cid]["stages"][s][1] / 1e9 / agg[cid]["wall_s"]

    # ---- contrasts (SPEC vs LGC, paired by cell index) ----
    br, dsync, dhoff, dfall, hstars, rates = [], [], [], [], [], []
    for i in (1, 2, 3):
        L, S = agg[f"LGC_{i}"], agg[f"SPEC_{i}"]
        br.append(S["bytes"] / L["bytes"] if L["bytes"] else float("inf"))
        dsync.append(share(f"SPEC_{i}", "sync_wait") - share(f"LGC_{i}", "sync_wait"))
        dhoff.append(share(f"SPEC_{i}", "expert_completion_handoff") - share(f"LGC_{i}", "expert_completion_handoff"))
        dfall.append(share(f"SPEC_{i}", "gpu_route_fallback") - share(f"LGC_{i}", "gpu_route_fallback"))
        if S["bytes"] > L["bytes"]:
            hstars.append(1.0 - L["bytes"] / S["bytes"])
        else:
            hstars.append(0.0)  # no extra traffic -> break-even trivially satisfied
        dT = S["wall_s"] - L["wall_s"]
        dB = (S["bytes"] - L["bytes"])
        rates.append(dB / dT if dT > 0 and dB > 0 else float("nan"))

    def med(x):
        v = sorted(x); n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    m_br, m_sync, m_hoff, m_fall = med(br), med(dsync), med(dhoff), med(dfall)
    # ---- decision tree (preregistered thresholds) ----
    d1 = m_br >= 1.15 and m_sync <= 0.05
    d2 = m_sync > 0.05 and m_br < 1.15
    d3 = m_hoff > 0.05 and not (d1 or d2)
    mixed = m_br >= 1.15 and m_sync > 0.05
    if mixed:
        label = "MIXED(policy+scheduling)"
    elif d1:
        label = "D1-OVER-FETCH-DOMINATED"
    elif d2:
        label = "D2-STALL-DOMINATED"
    elif d3:
        label = "D3-HANDOFF-DOMINATED"
    else:
        label = None
    for cid in CELLS:
        a = agg[cid]
        sh = {s.split("_")[0] if s != "expert_completion_handoff" else "handoff":
              round(a["stages"][s][1] / 1e9 / a["wall_s"], 4) for s in STAGES}
        print(f"{cid}: wall={a['wall_s']:.2f}s B={a['bytes']/2**20:.1f}MiB "
              f"GiB/s={a['bytes']/2**30/(a['stages']['expert_dispatch'][1]/1e9):.2f} shares={sh}")
    print(f"\nCONTRAST SPEC-vs-LGC: bytes_ratio med[range]={m_br:.3f}[{min(br):.3f},{max(br):.3f}] "
          f"Δsync={m_sync:+.4f} Δhandoff={m_hoff:+.4f} Δfallback={m_fall:+.4f}")
    print(f"BREAK-EVEN traffic h* = fraction of SPEC expert traffic that must be useful: "
          f"med {med(hstars):.3f} [{min(hstars):.3f},{max(hstars):.3f}] "
          f"(necessary condition for time break-even, not sufficient)")
    print(f"implied added-traffic rate med {med(rates):.2f} GiB/s")
    print(f"FOLLOW-UP: D1->prefetch-policy-break-even D2->scheduling D3->exec-path-handoff")
    if not label:
        fail(3, "VERDICT: INCONCLUSIVE (no preregistered branch armed)")
    print(f"VERDICT: DIAGNOSIS-{label}")
    sys.exit(0)

if __name__ == "__main__":
    main()
