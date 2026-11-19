# CORRECTION-20261118 — exp825 stage-2 interpretation revised

Mythos 5.2 review (MYTHOS-NEXTSTEPS-20261118.md, this directory) found a phase confound in the
stage-2 battery that RESULTS-825B.md does not account for:

- Run order placed b8's rounds 1-2 and b1's round 1 in an early slow phase (~2,665 s across five
  blocks) that ends regardless of arm; the fast-phase medians were compared across that boundary.
- Fast-phase per-step walls: b1 88.5-89.4 ms, b2 689.7-689.8, b4 930.2-952.9, b8 1,037.9 (n=1)
  -> b8 fast-phase throughput ~7.71 tok/s vs b1 ~11.18-11.30. Batching still loses end-to-end,
  but "-89.8%" and "b8 never stabilized" are artifacts of the phase draw, not steady-state facts.
- Within b>=2, throughput RISES with batch (2.90 -> 4.2 -> 7.71). The b1->b2 jump (7.8x per-step)
  is the dominant cost and may be path-confounded (native single-token branch vs HF multi-token
  dispatcher branch with mask-gather + host-sync accumulate; exp825 stage 2 lacked an HF-loop b1
  arm to separate path from batch).
- Prior provenance corrected: "98.4% orchestration" and "7.2x amortization" originate in
  EXP-803.md:26,31 (attention bucket decomposition on RTX 6000 Ada), not exp810, and never
  predicted engine walls.

Sealed artifact (exp825-batchwalls.json, sha 0fbdc4b5...) is UNCHANGED and remains the data of
record; the block-level re-read in run order stands as published. The INTERPRETATION above
supersedes the "no amortization, -89.8%" headline. Follow-up experiments (path x batch
decomposition, slow-phase characterization) are specified in MYTHOS-NEXTSTEPS-20261118.md.
