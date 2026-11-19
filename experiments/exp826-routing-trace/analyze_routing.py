#!/usr/bin/env python3
"""exp826 stage-0 analysis: step-local expert overlap from 16-prompt router traces.
Input: exp826-routing-steps.json (sha256 05e9ae7d71a5cab4... full sha in FREEZE).
Structure: per_prompt_layer_experts[p]["16"] = flat call-order list; layer = i%16, step = i//16.
All published numbers below are printed by this script from the sealed artifact."""
import json, itertools, statistics, random, sys
d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "exp826-routing-steps.json"))
raw = d["per_prompt_layer_experts"]; prompts = sorted(raw, key=int)
NL = 16; gen_len = {p: len(raw[p]["16"]) // NL for p in prompts}
tr = {(p, i // NL, i % NL): set(ids) for p in prompts for i, ids in enumerate(raw[p]["16"])}
def jacc(a, b): return len(a & b) / len(a | b)
per_step = []
for s in range(64):
    act = [p for p in prompts if s < gen_len[p]]
    if len(act) < 8: break
    vals = []
    for L in range(NL):
        sets = [tr[(p, s, L)] for p in act]
        vals += [jacc(a, b) for a, b in itertools.combinations(sets, 2)]
    per_step.append(statistics.mean(vals))
print("step_aligned_overlap_mean %.4f" % statistics.mean(per_step))
print("step0_prefill_overlap %.4f" % per_step[0])
print("decode_steps1plus_overlap_mean %.4f" % statistics.mean(per_step[1:]))
act8 = [p for p in prompts if gen_len[p] >= 8]
random.seed(20261118)
us2 = []
for _ in range(60):
    ps = random.sample(act8, 8)
    for s in (6, 10, 14):
        for L in range(NL):
            us2.append(len(set().union(*[tr[(p, s, L)] for p in ps])))
print("b8_random_distinct_per_step_layer_mean %.1f min %d max %d" % (statistics.mean(us2), min(us2), max(us2)))
def wset(p, L, s0=0, s1=8):
    u = set()
    for s in range(s0, min(s1, gen_len[p])): u |= tr[(p, s, L)]
    return u
pw = {frozenset((a,b)): statistics.mean(jacc(wset(a,L), wset(b,L)) for L in range(NL)) for a,b in itertools.combinations(act8,2)}
un = sorted(act8); pairs = []
while len(un) >= 2:
    a = un.pop(0); b = max(un, key=lambda q: pw[frozenset((a,q))])
    un.remove(b); pairs.append((a, b, pw[frozenset((a,b))]))
allv = list(pw.values())
print("greedy_first8_pairs_mean %.4f random_pair_mean %.4f best_pair %.4f" % (statistics.mean([x[2] for x in pairs]), statistics.mean(allv), max(allv)))
from collections import Counter
for L in (0, 8, 15):
    c = Counter()
    for p in prompts:
        for s in range(0, min(16, gen_len[p])): c.update(tr[(p, s, L)])
    tot = sum(c.values())
    print("layer%d top8_hot_share %.2f distinct_used %d/64" % (L, sum(n for _,n in c.most_common(8))/tot, len(c)))
