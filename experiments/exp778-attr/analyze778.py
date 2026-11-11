#!/usr/bin/env python3
"""exp778 analyzer: attribute decode residual from exp777 py-spy raw traces.

Input: /home/mfeth/exp777/out/PY_R075.pyspy (primary, sha16 3b0dac1d4487be3a)
and PY_R100.pyspy (consistency, sha16 77b5225ce0896c96). Collapsed-stack
format: 'frame;frame;...;frame count' per line, 50 Hz sampling.

Buckets (first-match priority over the WHOLE stack line; names from source
code: engine_arm776.py, transformers generation, HF modeling_olmoe forwards,
moe_infinity store paths — not derived from peeking at results):
  LOAD    from_pretrained|safetensors|serialization|load_checkpoint|
          load_state_dict|setup_archer|MoE.__init__|architectures
  EXPERT  moe_infinity/memory|moe_infinity/_store|expert_prefetcher|
          ExpertStore|expert_store
  ATTN    Attention|_attn|sdpa|rotary
  MLPRT   SparseMoeBlock|Mlp|gate_proj|up_proj|down_proj|Linear
  NORMEMB Norm|embed_tokens|Embedding|lm_head
  GENLOOP generation|_sample|sampler|engine_arm776|tokenize|stopping|
          logits_processor
  OTHER   (anything else)

Denominator for shares = non-LOAD samples (model load is outside the timed
W metric). LOAD share reported separately. Primary verdict on PY_R075;
PY_R100 rank-order agreement is report-only.

rc map:
  9 IDENTIFY-FAIL  input sha mismatch / unparseable
  4 DATA-FAIL      zero samples or zero non-LOAD samples
  1 ATTRIBUTED     top non-LOAD bucket share >= 0.30
  2 PARTIAL        top share in [0.17, 0.30)
  7 DIFFUSE        top share < 0.17 (floor 1/6 = 16.7%)
"""
import os, re, sys, hashlib

SHA = {"PY_R075": "3b0dac1d4487be3a", "PY_R100": "77b5225ce0896c96"}
BUCKETS = [
    ("LOAD", re.compile(r"from_pretrained|safetensors|serialization|load_checkpoint|load_state_dict|setup_archer|MoE\.__init__|architectures")),
    ("EXPERT", re.compile(r"moe_infinity/memory|moe_infinity/_store|expert_prefetcher|ExpertStore|expert_store")),
    ("ATTN", re.compile(r"Attention|_attn|sdpa|rotary")),
    ("MLPRT", re.compile(r"SparseMoeBlock|Mlp|gate_proj|up_proj|down_proj|Linear")),
    ("NORMEMB", re.compile(r"Norm|embed_tokens|Embedding|lm_head")),
    ("GENLOOP", re.compile(r"generation|_sample|sampler|engine_arm776|tokenize|stopping|logits_processor")),
]

def parse(path):
    counts = {b[0]: 0 for b in BUCKETS}
    counts["OTHER"] = 0
    load, total = 0, 0
    with open(path, errors="replace") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln:
                continue
            try:
                stack, n = ln.rsplit(" ", 1)
                n = int(n)
            except ValueError:
                continue
            total += n
            for name, rx in BUCKETS:
                if rx.search(stack):
                    counts[name] += n
                    break
            else:
                counts["OTHER"] += n
    return counts, total

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    vdir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(vdir, exist_ok=True)
    L = ["exp778 residual attribution from exp777 py-spy traces"]
    def fin(rc):
        txt = "\n".join(L)
        print(txt); print(f"rc={rc}")
        open(os.path.join(vdir, "verdict778.txt"), "w").write(txt + f"\nrc={rc}\n")
        return rc
    res = {}
    for cid in ["PY_R075", "PY_R100"]:
        p = os.path.join(d, "out", cid + ".pyspy")
        if not os.path.exists(p):
            L.append(f"IDENTIFY-FAIL missing {cid}.pyspy"); return fin(9)
        sha = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
        if sha != SHA[cid]:
            L.append(f"IDENTIFY-FAIL {cid} sha {sha} != {SHA[cid]}"); return fin(9)
        res[cid] = parse(p)
    for cid in ["PY_R075", "PY_R100"]:
        counts, total = res[cid]
        if total <= 0:
            L.append(f"DATA-FAIL {cid} zero samples"); return fin(4)
        nonload = total - counts["LOAD"]
        if nonload <= 0:
            L.append(f"DATA-FAIL {cid} zero non-LOAD samples"); return fin(4)
        L.append(f"{cid}: total={total} LOAD={counts['LOAD']} ({counts['LOAD']/total:.1%} of samples, excluded) nonLOAD={nonload}")
        ranked = sorted(((c, n) for c, n in counts.items() if c != "LOAD"), key=lambda kv: -kv[1])
        for c, n in ranked:
            L.append(f"  {cid} {c:8s} {n:8d} {n/nonload:7.1%}")
        res[cid + "_ranked"] = ranked
        res[cid + "_nonload"] = nonload
    top, topn = res["PY_R075_ranked"][0]
    share = topn / res["PY_R075_nonload"]
    L.append(f"primary PY_R075 top non-LOAD bucket: {top} share={share:.3f}")
    r100 = [c for c, _ in res["PY_R100_ranked"]]
    agree = r100.index(top) if top in r100 else -1
    L.append(f"PY_R100 rank agreement: {top} is rank {agree+1}/7 there (report-only)")
    L.append(f"EXPERT share of non-LOAD (consistency vs exp777 0.04% headroom, report-only): "
             f"{res['PY_R075'][0].get('EXPERT',0)/res['PY_R075_nonload']:.1%}")
    if share >= 0.30:
        L.append(f"ATTRIBUTED: {top} holds >=30% of non-LOAD decode samples — successor lane targets {top}"); return fin(1)
    if share >= 0.17:
        L.append(f"PARTIAL: {top} in [17%,30%) — instrument deeper before committing a lane"); return fin(2)
    L.append("DIFFUSE: no bucket >=17% of non-LOAD samples at Python level (floor 1/6=16.7%) — successor = native (--native) profiling"); return fin(7)

if __name__ == "__main__":
    sys.exit(main())
