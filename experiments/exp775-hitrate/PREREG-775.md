# PREREG-775 — hit-rate retention under the async double-buffer's stale lists

**Hypothesis.** exp773/774 reclaim the spec-prefetch wall cost by consuming
the *previous* call's topk list (one call staler than the blocking path).
exp772 showed k=4-stale lists cost ~nothing in wall time, so one-call
staleness should not measurably reduce prefetch coverage either — but this
was never measured directly. If coverage holds, the upstream story is
complete; if it erodes, the wall numbers already bound the cost and a
2-deep ring is the named successor.

**Metric (frozen, offline, zero added synchronization).** patch775.py logs,
per `speculative_prefetch` call, the CPU-resident list only (DB path: the
consumed list; blocking path: the freshly computed list). Coverage of the
next call's need:
- SPEC (fresh): hit(t) = |L_t ∩ L_{t+1}| / |L_{t+1}| — lag-1
- DB (stale): hit(t) = |C_t ∩ C_{t+2}| / |C_{t+2}| with C_t = L_{t-1} — lag-2
Pairs spanning call gaps > 1.0 s (prompt boundaries) are excluded.

**Cells.** Both on ONE instrumented build (src775 = src753 + patch775.py;
async-dbuf logic byte-identical to exp773's): `PY_SPEC` (EXP773_DB unset,
blocking) and `PY_DB` (EXP773_DB=1). Internal validity by construction.
Workload = prompts774.json byte-identical (24 prompts × 64 tok) so walls
compare to exp774 sealed references. py-spy spawn 50 Hz kept on (same
envelope; walls are profiled in both experiments).

**Frozen decision rule** (analyze775.py). Wall covariate gate first:
each arm within ±25% of its exp774 reference (SPEC 212.13 s, DB 179.72 s)
— else rc=4 (instrumentation perturbed the system; hit numbers void).
≥ 200 valid pairs per arm. D = hit(DB) − hit(SPEC):
- rc=1 RETAINED: D ≥ −0.02
- rc=2 ERODED: −0.10 ≤ D < −0.02
- rc=7 SEVERE: D < −0.10
rc=9 IDENTIFY / rc=4 DATA as in the lineage.

**Void conditions.** Any post-freeze change to analyzer/engine/sampler/
src775/prompts; py-spy version ≠ PYSPY.txt; busy-gate roster (exp746…
exp767, exp771–775); logging observed to sync (by construction it cannot —
logged lists are already on the CPU).

**Success criterion.** rc=1 → chain complete for upstreaming: exp773 patch
+ exp774 scale/replicate + exp775 coverage retention. Successor = upstream
PR. rc=2/7 → successor ring-depth-2 (consume the freshest armed buffer)
with these numbers as the baseline.
