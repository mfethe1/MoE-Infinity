# PREREG-771 — function-level CPU attribution on the main thread

**Question.** exp770 (D1 MAIN-BOUND) showed the spec-prefetch cost is burned
on the GIL-holding main thread (67% of Δcpu). Which python function(s) on
that thread carry it?

**Design.** 2 cells, envelope verbatim from exp769/770 (OLMoE-1B-7B, src753 @
b7f6ca4, lcnu r=0.75, threads 4, 6 prompts × 64 tok, warmup 1). Cells:
`PY_LGC` (off off off) vs `PY_SPEC` (spec-prefetch on). Engine and OS sampler
byte-identical to exp770 (1f119bd017985083 / 9c39353053718c1c — oscsv/tidcsv
kept as cross-checks only). NEW: py-spy 0.4.3 in SPAWN mode (attach needs
sudo ptrace — denied on this box; spawn proven in exp767 and re-probed
2026-11-11: rc=0, 299 samples, 0 errors). The engine runs under
`py-spy record -r 50 -f raw -o out/$ID.pyspy -- python3 engine_arm771.py ...`
(python frames only, non-native, 50 Hz, raw collapsed; py-spy exits with the
engine; missing py-spy → runner exits 4 PYSPY-FAIL). Observer effect is
symmetric across arms; we attribute *relative* CPU, not wall.

**Aggregation.** Leaf frame of each collapsed stack line; deltas in samples;
seconds = samples/50. Aggregation covers the whole run — load-phase frames
cancel in the arm delta (identical build/inputs both arms).

**Frozen decision rule** (analyze771.py, battery 8/8 before staging).
- rc=9 IDENTIFY-FAIL: SRC_HEAD ≠ b7f6ca4
- rc=4 DATA-FAIL: missing/short artifacts; json rows<6; <2000 samples/arm
- DcpuS = (S_samples − L_samples)/50; |DcpuS| < 2.0 s → rc=5 NO-SIGNAL;
  ≤ −2.0 s → rc=8 REVERSED
- positive leaf deltas ranked; pos_sum = Σ positive deltas
  - rc=1 F-TOP: top1 ≥ max(1.0 s, 0.4·pos_sum)
  - rc=2 F-PAIR: top1+top2 ≥ max(2.0 s, 0.6·pos_sum)
  - rc=7 F-DIFFUSE: otherwise

**Void conditions.** Any change to analyzer/sampler/engine after freeze;
py-spy version different from out/PYSPY.txt at adjudication; interference
gate tripped (busy-gate units exp746–exp767 + exp770 + exp771).

**Success criterion.** rc ∈ {1,2} names the function (or pair) carrying the
main-thread cost → exp772 targets it for amortization/batching. rc=7 falls
back to line-level attribution.
