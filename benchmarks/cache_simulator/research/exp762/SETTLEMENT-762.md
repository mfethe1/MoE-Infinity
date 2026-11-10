# SETTLEMENT-762 — 2026-11-10

## Verdict chain
1. Frozen analyzer (sha ba2cf1f4…, per FREEZE-762.txt 4d8a9026): INCONCLUSIVE exit 3 —
   0 valid cells, all 12 excluded via marker(BANNER-FAIL). Recorded verbatim in
   out/verdict.frozen-INCONCLUSIVE.txt (copy of out/verdict.txt). Cause: runner banner
   gate greps literal 'exp752 mode=RC'; engine emits 'exp752 mode=%d' (RC resolves to 2).
   Never-matchable grep → false marker on every cell (family: this exact bug class voided
   attempt-1's identity gate; here it hit the analyzer's marker layer).
2. SETTLE-NOTES-762.md (pre-registered 20:52Z, BEFORE outcomes examined) rule: cells whose
   log contains 'exp752 mode=2' are banner-false-alarms; banner identity PROVEN by mode=2
   (sealed exp760: 24/24 RC logs printed mode=2; exp759 mode-0 cells printed mode=0).
3. Banner proof on this run: 12/12 logs contain 'exp752 mode=2'; FLAGGED/FAILED/BADIO empty;
   precell 12 QUIET / 0 TIMEOUT; 12/12 cell jsons + 12/12 io profiles.
4. Addendum analyzer addendum_analyze762.py (sha 3e2a9989…): byte-identical to frozen except
   the banner re-adjudication block (diff verified; fixture-tested both directions: mode=2
   → re-adjudicated, mode=0 → stays excluded). Run read-only on out/ → verdict.addendum.txt
   (sha c59a5f7e…).

## Adjudicated result (pending independent review)
- All 12 cells valid; token-identity gate PASSED (byte-identical out_ids across all 4 arms —
  the overlap path does not alter greedy decode numerics).
- Cell means (ms/tok, lower faster): LGC 83.64 | SPEC 101.39 | OVR 91.40 | ENF 93.28.
- PRIMARY OVR-vs-LGC: −9.28% [CI95 −10.97, −7.81] → OVR significantly SLOWER. Primary
  endpoint (≥ +5%) decisively failed.
- SPEC-vs-LGC: −21.23% [−23.79, −18.72] — speculative prefetch alone costs ~21%.
- OVR-vs-SPEC: +9.86% [8.37, 11.39] — the overlap machinery recovers ~10 of the 21 lost
  points. Mechanism works; its enabler (spec-prefetch policy) is net-negative.
- ENF-vs-OVR: −2.06% [−4.36, 0.08] — budget enforcement ≈ free.
- Arms echo-verified: LGC off/off/off; SPEC on/off/off; OVR on/on/off (overlap machinery on,
  policy off); ENF on/on/enforce; gpu_route off everywhere.

## Verdict: NO-GAIN (DECISION-TREE B2) — honest negative, admitted
Reading: at lcnu r=0.75 with this predictor, speculative expert-prefetch is a net −21%;
in-engine io-overlap recovers roughly half but cannot reach baseline. The "io-overlap-in-engine
as free upside" hypothesis is falsified AS SHIPPED; overlap is a recovery mechanism, valuable
only under a prefetch policy that breaks even.

## Consequences (per DECISION-TREE-762.md B2)
- BELIEFS: io-overlap-in-engine re-scored DOWN (was 11.29 #1); new conditional thread:
  prefetch-policy break-even (predictor hit-rate / skip-on-low-confidence).
- Next: exp763 DIAGNOSIS (zero-GPU): mine the 12 io.jsonl traces (340,800 events) for
  prefetch hit-rate, bandwidth split, queue depth — explain the 21% SPEC cost mechanically.
- No PR #353 enablement post (B1 branch dead); honest-negative post instead after review.

## Independent review
- Review pass 1 (gpt-sol, 2026-11-10T21:2xZ): VERDICT FAIL — VALID, quoted contradiction:
  frozen analyzer requires "no FAILED/BANNER-FAIL/BADIO entry", but unconditioned
  `failed -= banner_false` lifted exclusions for cells ALSO in FAILED/BADIO (bypass
  defect). Scope check: real out/FAILED and out/BADIO are EMPTY → defect could not and
  did not alter the exp762 verdict (re-run after fix: output byte-identical, RC=1).
- Fix: `failed -= (banner_false - hard)` where hard = FAILED∪BADIO ids; kept-excluded
  list printed. Addendum sha 3e2a9989 → d4438671 (Winnie re-staged; verdict.addendum2.txt
  byte-identical to verdict.addendum.txt). Double-marker fixtures verified both
  directions (BANNER-FAIL+FAILED → marker(FAILED,BANNER-FAIL) rc3; BANNER-FAIL+BADIO →
  marker(BANNER-FAIL,BADIO) rc3; clean → 12 re-adjudicated rc1; mode=0 → excluded rc3).
- Review pass 2 (confirmation of fix): **APPROVED** — "APPROVE the fixed addendum
  (d4438671…) and NO-GAIN adjudication. Diff/AST checks confirm only banner
  re-adjudication changes behavior; Independent replay passed 9/9 cases … Winnie rerun:
  12/12 valid, token identity independently confirmed, rc1. Output is byte-identical
  under reconstructed pre-fix logic." (gpt-6.1-sol, 2026-11-10T21:24Z,
  transcript deleg_38049e72/task-0.log).
- **SETTLEMENT FINAL: NO-GAIN (B2) — admitted.**

## Cross-lane resolution (tier1 lane 7687a6bf1295, reply 20:45Z)
- Their CG3 rerun ran as unit exp761run2 (20:16:54Z) — our busy list predated that unit
  name (not detached after all). exp761 SEALED 20:37:39Z, verdict INCONCLUSIVE(n=10),
  0/10 divergent, seal 5b599f19afec090b.
- Our attempt-3 launched 20:43:27Z — AFTER their seal → prereg launch condition satisfied
  for the data-producing attempt. Only void attempt-2 overlapped their window (2 min).
- GPU1 free until ~22:15Z per their note; NVML-query-vs-compute-tenant distinction
  carried as future prereg amendment candidate (their lane, not applied post-hoc).
