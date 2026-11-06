# exp732 PREREG — FusedCostFit: exp729's fused per-key record ported to the N=2 CostFit head

Lane 79990 / STACK-1001. Written 2026-11-06 before any smoke or real run. Pre-registered CONFIRMED branch of exp729
(ADDENDUM64: FusedCostFit3 PAYOFF-CONFIRMED + SAVING, worst cell x0.9605, struct x0.374–0.627).

## Question
Does the fused layout (one Key -> list record for every per-key field, with the leaf methods re-expressed over the
record) still pay at N=2 — the CostFit head (lcnu vs s3fifo arbiter, sealed `policies_costfit.py`, class parameters
MARGIN 0.005 / GAMMA 0.0025 / HALF_LIFE 32768 = the exp714 joint 2-trace bar-constrained BO center) — where there are
only 5 per-key fields (LCNU last/ema/count/first, S3-FIFO freq) instead of 10, so fewer lookups are saved and the
fixed list overhead weighs more? And what does an array-of-struct C layout cost vs struct-of-arrays at real occupancy?

## Arms (`policies_fused2.py`)
- `costfit` (A): sealed CostFit via `build_policy("costfit")` + `geometry_kwargs("costfit")`.
- `fused2` (B): `FusedCostFit` = sealed CostFit arbiter; inner leaves subclass the sealed LCNU / S3-FIFO with the
  per-key methods copied byte-for-byte from exp729's sealed `policies_fused.py` (`_FusedLCNU`, `_FusedS3`; verified by
  diff — only the module-global NSLOT differs, 10 -> 5) and offsets lcnu rec[0:4], s3fifo rec[4]. No parameter override.

## Design (runner `run_fused2.py` = sealed exp729 runner with asserted substitutions only)
- Units per cell: `null` costfit vs costfit (A/A validity gate); `fused2` costfit vs FusedCostFit (PRIMARY).
- Streams: qwen30b (1,424,640 accesses) and granite (638,208), full, prefill skip, ignore_layers 0.
- Caps 256, 1024, 4096, 262144 (ceiling). 8 rounds (MIN 5), Random(732) shuffles cap and stream order per round.
- Each (round, stream) in a fresh spawned process at QOS_USER_INTERACTIVE; per unit 4 timed replays ABBA (even
  rounds) / BAAB (odd rounds); pair ratio = sum(B thread_ns) / sum(A thread_ns). Cell stat = median over rounds,
  q25/q75 linear interpolation. proc/wall clocks recorded, descriptive only.
- Wall budget 5.5 h; exp729 runner machinery, ladder and 15-case self-test unchanged (self-test must pass 15/15 before
  measurement).

## Gates — frozen ladder (first match wins; R3 = fused2 argmax-cell thread median, IQR of that cell)
1. SEALED-FAIL: any sealed dependency sha drift (16 deps incl. exp729 `policies_fused.py`), or ANY timed replay
   hit_rate != exp718 PASS-1 `costfit` hit rate for its (stream, cap), or round-0 terminal full state of either B arm !=
   its paired costfit A arm (arbiter choice/switches/since/mass/sw_mass/credited, both leaves' resident/hits/misses,
   LCNU visits/by_layer and every [last, ema, count, first], S3-FIFO small/main/ghost and every freq), or round-0 A-arm
   census != sealed `structure_census`, or round-0 census incomplete (16/16).
2. INCOMPLETE-BUDGET: complete rounds < 5.
3. TIME-INVALID: A/A null pooled median of 8 cell medians outside [0.97, 1.03] or any cell median outside [0.93, 1.07].
4. PAYOFF-UNRESOLVED: R3 IQR straddles 1.10 or 1.35 (q25 <= t < q75).
5. PAYOFF-CONFIRMED: R3 <= 1.10. 6. PAYOFF-MARGINAL: R3 <= 1.35. 7. PAYOFF-REJECTED otherwise.

Economics qualifier (independent of the ladder): SAVING iff fused2/costfit per-key struct_bytes (getsizeof of per-key
containers, exp675a/CEN methodology) <= 0.80 at ALL 8 cells (round-0 census); else NO-SAVING. Same bar as exp729.

## Descriptive (non-gating, frozen formula in `policies_fused2.py`)
C-level byte model from the round-0 fused census: SoA = 5 per-field open-addressing maps at load 0.75
(u32 key + value padded: last 8, ema 16, count 8, first 8 B per LCNU-occupied key; freq 8 B per S3-occupied key);
AoS = one map of 32 B records {u32 key, u32 last, u32 count, u32 first, f64 ema, u8 freq, pad} per key at load 0.75.
Reported: aos_bytes / soa_bytes per cell. Also clock robustness (proc/wall) and leave-one-round-out.

## Predictions (stated before smoke)
- (a) PAYOFF-CONFIRMED with R3 in [0.90, 1.02] — fewer lookups saved than at N=3, so smaller speed gain.
- (b) Struct ratio fused2/costfit in [0.60, 0.90] at all cells; P(SAVING) ~ 0.5 — honest uncertainty: the 4 LCNU dicts
  hold every key ever seen, a 5-slot list costs ~96 B, so the margin vs the 0.80 bar is thin.
- (c) C model AoS/SoA in [0.75, 1.00] (AoS pays 32 B for every key incl. S3-absent ones; SoA pays 4 maps).

## Consequence
- CONFIRMED + SAVING: fused record is the recommended metadata layout for BOTH CostFit heads (N=2 and N=3); hand the
  AoS byte model to the engine lane. CONFIRMED + NO-SAVING: speed only; layout choice at N=2 becomes a C-level
  question (AoS model decides). MARGINAL/REJECTED: the exp729 win is N-dependent; keep N=2 per-field maps.
- TIME-INVALID / SEALED-FAIL: no claim; diagnose before any re-run (sealed experiments are never re-launched).

## Smoke (disclosed, never a result)
SMOKE=1: 2 rounds, caps 256/4096, first 40,000 accesses; checks determinism, round-0 parity + census 8/8, self-test.
Freeze `shasum -a 256` of PREREG/runner/policies/sealed_deps/smoke.log into ARTIFACT.sha256 BEFORE the real run.
