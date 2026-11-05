# ADDENDUM58 — exp715: shipped engine eviction-policy port vs simulator, 3 full real decode traces

**Verdict (pre-registered ladder, PREREG.md frozen at e85a16a): `PARITY-HOLDS:DEFAULT-CHALLENGED|OVERHEAD-OK`**

Upstream MoE-Infinity ported the cache-simulator policies to C++ (#339) and made LCNU the
engine default (#341). This experiment runs the pinned upstream port (`UPSTREAM_SHA`
033798811664) and the upstream Python simulator on our three full decode-only streams
(granite-3.1-moe-3b N=638208, qwen3-30b-a3b hi N=786432, lo N=638208) at the sealed exp704
capacity grids, 13 policies, 351 cells.

## Bars
- **P1 exact parity: PASS.** C++ == Python simulator hit count in 351/351 cells; C++ rerun bit-identical 351/351.
  This covers granite-3.1-moe, a family upstream never traced, and the full streams (upstream checked 200k accesses of one trace).
- **P2 sealed anchor: PASS.** C++ LCNU rate == sealed exp704 LCNU in 27/27 cells (max |diff| 0.0e+00).
- **P3 LCNU default within 0.5pp of best in >=25/27: FAIL (17/27).**
- **P4 overhead <=1000 ns/access: PASS.** LCNU worst median ns/access: granite 447, hi 663, lo 685
  (Mack M4, loadavg 5.3 with another experiment running). At 48 layers x top-8 that is ~255 us CPU per decode token for the policy alone.

## Where the default loses (descriptive, derived here from raw cells)
- **granite** (distinct 1262): LCNU best through cap 768; first loss at cap 896 (0.71x distinct); worst gap 0.23pp at cap 1024 (LCNU 0.9708 vs s3fifo 0.9732); S3-FIFO is best in 2/9 cells.
- **hi** (distinct 5097): LCNU best through cap 1152; first loss at cap 1280 (0.25x distinct); worst gap 1.83pp at cap 1792 (LCNU 0.8752 vs s3fifo 0.8935); S3-FIFO is best in 5/9 cells.
- **lo** (distinct 5842): LCNU best through cap 1024; first loss at cap 1152 (0.20x distinct); worst gap 3.27pp at cap 2048 (LCNU 0.8229 vs s3fifo 0.8556); S3-FIFO is best in 6/9 cells.
- LCNU loses to S3-FIFO in 13/27 cells, always a contiguous upper tail of each grid; where LCNU is best it leads the runner-up by 0.13-3.63pp.
- A two-policy rule (LCNU or S3-FIFO, whichever is better per cell) is within 0.000pp of the best of all 13 policies in every cell — the other 11 policies add nothing on this traffic.
- SIEVE trails LCNU by >= 4.2pp in every cell; it should not be offered as a residency policy for MoE decode without a warning.

## Reading
The port is faithful: no parity defect on 351 real cells. The default choice is right for
memory-starved deployments (the case MoE offloading exists for) and wrong by up to
3.3pp once the cache holds about 0.20-0.25x of the distinct experts on qwen30b
(granite: 0.71x). The obvious follow-up is a capacity-aware default (LCNU below a crossover,
S3-FIFO above), pre-registered with the crossover fitted on two traces and tested on the third.

## Scope
Replay through `SimulateEvictionPolicy` only; not `ExpertResidencyManager` integration and no
latency/throughput claim. Real-engine measurement is being brought up on Winnie (exp716).

## Provenance
- result `exp715-engineparity.json` sha256 30ed8e34a11628bf2384d42204e2a04e98d0b138f52f71680a36a6cdfff73659
- frozen ARTIFACT.sha256 (== freeze commit e85a16a):
```
2eed7d25ce163700d8bea6f491eb209edefe1cb41d8d4aa3610709423dd773c2  run_engineparity.py
802c509399786c3776354b5a8f4fe8789c594bbedff715c055b7bb651c766b34  common.py
73fbb4e004fe64503123d06ca737797f97c787d3dd4a00fd91492b7f0f118c50  src/timing_driver.cpp
bcc8c7b696e0b69b830cd2eeef31e6dd122defc1ddbcfc525a8716035a60ef8c  PREREG.md
```
- adjudicator `gen_addendum58.py` recomputes every bar from raw per-cell counts; 390 internal checks PASS; runner wall 2111s, exit 0.
