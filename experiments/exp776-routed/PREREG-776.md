# PREREG-776 — routed-expert persistence vs heuristic coverage

**Hypothesis.** exp775 showed the shipped heuristic (mean-logits topk, k=2)
achieves ~0.03 lag-1 coverage against the next call's *list*. Two open
questions follow: (a) how well does that heuristic cover the next call's
TRUE need — the set of experts tokens actually route to; (b) does routing
persist across calls strongly enough that the previous step's routed set
predicts the next step's need? High persistence would also explain why the
no-spec-prefetch arm (LGC) keeps beating both prefetch arms: its recency
policy already exploits persistence.

**Measurement (frozen).** patch776.py on the async-dbuf config (one cell,
24 prompts × 64 tok, prompts774.json byte-identical). Under EXP776_LOG_OUT
the logging branch records per call: the fresh heuristic topk list and the
routed set (unique per-token argmax). Logging syncs per call — this run's
WALL is informational only and NOT comparable to exp774 refs; the metrics
are set overlaps computed offline by analyze776.py:
- Q2 persistence P = |R_t ∩ R_{t+1}| / |R_{t+1|}
- Q3 heuristic H = |L_t ∩ R_{t+1}| / |R_{t+1}|
- Q4 lift = P − H, with ceiling context k/mean|R|
Pairs spanning >1 s gaps (prompt boundaries) excluded; ≥ 200 valid pairs.

**Frozen decision rule.**
- rc=1 PREDICTIVE-LIFT: lift ≥ 0.15 AND P ≥ 0.40
- rc=2 MILD-LIFT: lift ≥ 0.05 (and not rc=1)
- rc=7 NO-LIFT: otherwise
rc=9 IDENTIFY / rc=4 DATA as in the lineage.

**Void conditions.** Any post-freeze change to analyzer/engine/sampler/
src776/prompts; py-spy version ≠ PYSPY.txt; busy-gate roster (exp746…exp767,
exp771–exp776).

**Successors.** rc=1 → exp777: routed-set retention (armed async, PR-#358
mechanics) as the predictor, wall-gated against LGC. rc=2 → quantify
prefetch-cost-vs-coverage before intervening. rc=7 → prediction class
closed; policy work (recency/LRU tuning) is the remaining lever.
