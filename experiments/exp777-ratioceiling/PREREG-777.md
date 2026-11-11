# PREREG-777 — residency-ratio wall ceiling

**Hypothesis.** With prediction closed (exp776b: same-layer persistence
0.172, heuristic 0.254 — both below viability), the only remaining lever on
expert-residency wall cost is the budget itself. The ceiling for ANY policy
improvement is the delta between the current budget (r=0.75) and the best
feasible budget. Measure W(r) for r ∈ {0.75, 0.90, 0.975, 1.0} on the
shipped path (src776, PR #358 behavior; exp776 logging dormant — no log env).

**Design.** 4 sequential cells, same build/prompts/workload as exp775/776
(24 prompts × 64 tok, OLMoE-1B-7B, lcnu, threads 4, py-spy 50 Hz). r=0.75 is
the covariate cell: must land within exp775 DB ref 182.66 ± 25% →
[137.00, 228.33]. A cell that fails (e.g. r=1.0 OOM) is recorded, not fatal:
r* = max feasible r with RC=0.

**Frozen decision rule.**
- headroom = (W(0.75) − W(r*)) / W(0.75)
- rc=1 LARGE-HEADROOM: headroom ≥ 0.10 → policy/budget lane has real room;
  successor exp778 attributes miss stalls (store instrumentation).
- rc=2 MILD-HEADROOM: 0.03 ≤ headroom < 0.10 → policy upside capped small.
- rc=7 NO-HEADROOM: headroom < 0.03 → residency policy lane CLOSED; residual
  lives outside expert residency.
- rc=4 DATA: BADIO / reference cell dirty or outside gate / no feasible r>0.75.
- rc=9 IDENTIFY: SRC_HEAD ≠ b7f6ca4…, ENV moei-776 line missing, src776 file
  sha ≠ 3571f714c811e1c7.

**Void conditions.** Post-freeze edits to runner/analyzer/src776/engine/
sampler/prompts; py-spy version drift; busy-gate roster (exp746…exp777).

**Interpretation guards.** Monotonicity of W over r is report-only. r=1.0
fully resident makes expert loads GPU-local; if it OOMs the ceiling is
measured at r* instead (documented, not voided).
