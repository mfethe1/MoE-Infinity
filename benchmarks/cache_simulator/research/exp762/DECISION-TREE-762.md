# EXP762 decision tree — pre-committed settle branches (written pre-run, 2026-11-10T20:2xZ)

Branches are keyed to analyze762.py verdicts + contrast signs. No post-hoc reinterpretation.

## B1: OVERLAP-GAIN (exit 0, CI95lo OVR-vs-LGC >= 5%)
- Direction io_overlap: append evidence per PREREG weights (w=0.75; w=1 if point >= 15%).
- exp763 = LINK-SENSITIVITY: same envelope, GPU0 (gen3x2, PCIe-bound 1.56 GB/s per exp720 H3).
  Prediction from exp720: engine-level overlap gain should GROW on the slower link
  (standalone PIPE/SER 1.51-1.55x GPU0 vs 1.21x GPU1). Prereg directional bar: OVR-vs-LGC on
  GPU0 strictly exceeds GPU1 point gain. Runner delta is one line (G=0) + freeze; stage after exp762 settles.
- Upstream post: config-level enablement guidance on PR #353 thread (numbers + cache-pressure caveat).
  Standing approval covers it.

## B2: NO-GAIN (exit 1) with SPEC-vs-LGC also < 5%
- Speculative prefetch does not help decode at ratio 0.75 / lcnu on this workload. Do NOT admit
  io_overlap engine-level support. w=0 evidence entry (honest negative), direction mean drops.
- exp763 = DIAGNOSIS: parse $ID.io.jsonl (MOE_INFINITY_PROFILE_IO) for stall fraction + prefetch
  issue/admit counts. Distinguish (a) transfers too small to matter at this ratio (VRAM residency
  absorbs working set -> try ratio 0.2 = forced offload-heavy regime), vs (b) scheduler never issues
  (bug/miswire), vs (c) issued but not overlapped (barrier still blocks). Each has a distinct fix;
  only (a) is a real negative for the direction (then the lever matters only at low ratio ->
  exp764 = ratio sweep 0.1/0.2/0.35 with OVR vs LGC).

## B3: SPEC-vs-LGC >= 5% but OVR-vs-SPEC ~ 0 (timing adds nothing)
- Prefetch itself helps; barrier timing irrelevant. Reframe: the win is residency anticipation,
  not overlap. Direction claim (>= 1.15x from double-buffered streaming) NOT supported at engine
  level; io_overlap evidence entry w=0.25 partial with reframed finding. exp763 = LINK-SENSITIVITY
  anyway (if timing never matters even on gen3x2, overlap thesis dies cleanly; if it matters only
  there, thesis is link-conditional — valuable either way).

## B4: ENF regresses vs OVR (point > +2% ms/tok)
- Budgeted admission costs throughput at these defaults. Record as covariate; candidate knob sweep
  (safety factor 0.9/0.95, window 512MB) ONLY if B1 holds — else drop ENF from future arms.

## B5: INCONCLUSIVE (valid < 3 any arm) or IDENTIFY-FAIL (exit 9)
- One rerun of failed cells (PREREG). If echo mismatches recur -> engine is overriding config ->
  halt lane, investigate ArcherConfig plumbing before any re-run; report to user.
- TOKEN-DIVERGENCE (exit 9 token gate): overlap path altered decode numerics — the A/B is
  invalid AND this is itself a material engine finding (config-only flags must not change token
  streams). Halt lane; preserve divergent cells' io profiles; candidate follow-up = numerics
  isolation (single-cell repro, expert-weight checksum under OVR vs LGC). Report to user same day.

## Cache-pressure tripwire (any branch)
- lockwarn > 0 on OVR/ENF cells: check whether those cells also show tok/s collapse
  (config help warns "All cached expert locked" failure mode at high ratio). If lockwarn>0 AND
  cell slow: mark cell as pressure-affected covariate, do NOT count as clean refutation; candidate
  follow-up = ratio 0.6 OVR-vs-LGC confirm pair.
