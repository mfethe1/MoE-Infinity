# RESULTS-M2B — exp828 M2b: dispatcher counters at b1 (0.50/0.65/0.75/0.90)

Run 2026-11-19T13:01-13:3xZ, unit exp828-m2b (sha e0414f34dab982ae5977e8f93f09de6a66bee1deb2163ca19c3d6bf882f3fd05,
FREEZE-828B.json). All 4 arms RC=0. Script-computed; pasted verbatim.

## Pooled tok/s per arm (32 forced tokens x 8 prompts, fresh engine per arm)
- 0.50 full 9.083 (first-six-clean 10.530; last two walls 5.387/4.564 s are outliers)
- 0.65: 10.124 | 0.75: 9.621 | 0.90: 7.392
- MOE_GROUPED_DECODE=1 here (exp791 protocol), NOT set in M1 — cross-refs to M1's
  75.3 ms/tok carry this label.

## Counter readings
- mean expert_cache_hit_rate: 0.50 -> 0.7814 | 0.65 -> 0.8738 | 0.75 -> 0.9465 | 0.90 -> 0.9488
- median exposed_fetch ms/tok: 0.19 (0.50) | 0.18 (0.65) | 0.18 (0.75) | 0.31 (0.90)
- Counter-API status in build 0337988: `expert_occupancy_bytes` is LIVE per-prompt
  (0.0 only in the post-load pre-generation snapshot): 0.50 flat 9.195 GB, 0.65 flat
  11.422 GB, 0.75 grows 12.681->13.335 GB, 0.90 grows 12.681->13.838 GB.
  `num_offloaded_experts` = 1024 in ALL arms (catalog constant, not live residency);
  `adaptive_memory_snapshot` hardcodes `accesses = 100`
  (model_offload.py line 867, verified live on Winnie post-run).

## Frozen-prediction outcomes
- P1 CONFIRM: hit(0.50)=0.7814 < 0.85 (real misses; not a fully-resident hot set).
- P2 CONFIRM: fetch 0.19 ms/tok = 0.25% of 75.3 ms/tok engine wall (threshold 15 ms).
  **Expert fetch-wait is negligible. The 2.36x streaming tax is NOT PCIe fetch wait.**
- P3 INCONCLUSIVE: |wall(0.65)-wall(0.50)|/wall(0.50): +11.5% on full arms (fails <5%),
  -3.1% like-for-like on both arms' first six prompts (passes). Cause: a stale
  first-launch watcher resumed the re-summon cron at ~13:06 inside arm 0.50's window
  (re-paused at 13:06:20Z); its last two prompts carry outlier walls. Hits 0.65 >= 0.50
  held. No claim issued either way.
- P4: completes TRUE; walls(0.90) slower than walls(0.75) TRUE (7.392 vs 9.621, -27% vs
  0.65 best); occupancy clause EVALUATED (counter live): device total 16,311 MiB
  (17.103 GB) -> requested 0.75 x = 12.827 GB vs observed max 13.335 GB (EXCEEDED
  +4.0%); requested 0.90 x = 15.393 GB vs observed max 13.838 GB (CAPPED). Cap holds
  at 0.90 but is soft at 0.75. P4 PARTIAL.

## Decision (frozen rule): #7 = in-engine dispatch elimination -> GO
P1 AND P2 confirm -> the 2.36x tax at b1 is CPU dispatch/handoff/op-count overhead
(consistent with M2a: ~700+ aten ops/step, router ops exactly 16/step), not expert
fetch wait and not residency pressure at <=0.65.

## Secondary observations (REPORTED, not gated)
- Ratio curve flattens 0.50<->0.65 then degrades: 0.75 -5%, 0.90 -27% vs 0.65 best —
  while fetch stays <=0.31 ms/tok and occupancy GROWS toward/past the cap at exactly
  those arms (12.681->13.335 GB at 0.75, +4.0% over requested; 12.681->13.838 GB at
  0.90): degradation consistent with cache-pool pressure (evict/admit churn), not
  fetch wait. REPORTED, not gated.
- Contamination note for the record: M1-style per-measure quiet gating contained the
  13:06 straggler event to two wall outliers; counters and hits were unaffected.

## Artifacts (full shas)
- m2b-0.5.json  0fe4933029bc798e7d0eb53ea59a1529035e8577d68a52dfdd98d52e662a4b53
- m2b-0.65.json 461d256ebff73f4560e83c90c42cb2081cc508a33faa53bcdcec9416c509ef48
- m2b-0.75.json 71868506ef65e449168845915cd3acb805f29e3625e2f2f5cf217c0a8ea3ee54
- m2b-0.9.json  0361edfea1c32189601b2a2a97cc89ca70e98e0714c0c7ff82fbdc6d984b25e1
