## 2026-11-19 gate-caught correction (post receipt #142)
- WRONG (RESULTS-M2B.md + receipt #142): "expert_occupancy_bytes = 0.0 in ALL arms
  (dead)" and P4 "NOT EVALUABLE". Cause: verifier read only vram_after_load
  (pre-generation snapshot; 0.0 expected there). Per-prompt reads are live.
- CORRECTED: occupancy live per-prompt; P4 EVALUATED -> PARTIAL (capped at 0.90,
  +4.0% over requested at 0.75); P3 sensitivity restated like-for-like (-3.1%,
  both arms first-six). Public correction queued for receipt #143 (post-once).
