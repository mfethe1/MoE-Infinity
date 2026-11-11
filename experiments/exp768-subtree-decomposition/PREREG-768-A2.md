# PREREG-768-A2 — attempt-2 floor correction (fresh prereg; attempt-1 sealed INCONCLUSIVE)

## Why attempt-2
Attempt-1 (FREEZE-768 84dd2eb137845228, analyze768.py 3ae61c7721aeaa9a) returned rc=3
INCONCLUSIVE with floor-fails `LGC:SPEC:0` and `SPEC:SPEC:188`. Structural flaw in the
attempt-1 floor rule, identified from the frozen output alone: the `speculative_prefetch`
subtree is a FEATURE-GATED region — it is necessarily absent (0 samples) in the LGC arm
(spec-prefetch off) and small in the SPEC arm (188 samples = 1.88 s). A symmetric
≥500/arm floor for it is unsatisfiable by construction. No data changed; the gate was
wrong. Same discipline as exp763 attempt-1 → attempt-2.

## Corrected gates (only change vs attempt-1)
- EAGER, WAIT (always-on code paths): unchanged, ≥ 500 samples per arm.
- SPEC (feature-gated): require ≥ 100 samples in the SPEC arm only; LGC-arm count is
  recorded (expected 0; a nonzero value would indicate mislabeled stacks and is reported).
  No additional noise floor is needed for the τ comparison on this subtree: with < 200
  samples its |Δ| cannot reach τ = 2.0 s, so the materiality bar is self-enforcing.
- τ = 2.0 s, MIN_COMBINED = 30,000, decision tree D1/D2/D3/D4 order: unchanged
  (see PREREG-768.md, which otherwise governs in full).

## Analyzer
`analyze768a2.py` — byte-identical decision logic to analyze768.py 3ae61c7721aeaa9a
except the floor block. Diff is renumber-minimal and will be recorded in FREEZE-768-A2.

## Fixture battery (fixtures768a2.py)
Attempt-1's 7 cases unchanged (expected rc values identical) + 1 new case:
- GATED-ZERO: SPEC subtree 0 in LGC arm / 188 in SPEC arm, all deltas < τ, floors met
  → must yield rc=5 (D3 NET-NULL), NOT rc=3.
Battery must be 8/8 PASS before freeze.
