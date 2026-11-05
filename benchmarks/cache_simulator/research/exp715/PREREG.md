# exp715 PREREG — shipped engine eviction-policy port vs simulator on 3 independent real traces

Frozen BEFORE the full run. Smoke (SMOKE=1, first 60k accesses, det caps only) was run to
validate the harness; its numbers are NOT results.

## Question
Upstream EfficientMoE/MoE-Infinity merged C++ ports of the cache-simulator policies
(PR #339, `core/prefetch/eviction_policy.cpp`) and made LCNU (alpha 0.3, beta 0.5,
prior top_k/experts, decode-only statistics) the engine default (#341). Upstream checked
parity on fuzzed traces and on 200k accesses of one Qwen3-30B-A3B decode trace. Does the
shipped port reproduce the simulator exactly on our three FULL real decode streams
(granite-3.1-moe-3b — a model family upstream never traced — and qwen3-30b hi/lo), is LCNU
the right default among the 13 shipped policies on that traffic, and what does the port
cost per access?

## Pinned inputs
- Upstream source: `UPSTREAM_SHA` (upstream/main at freeze). Files copied unmodified:
  `src/prefetch/eviction_policy.{h,cpp}`, `src/eviction_policy_driver.cpp`,
  `ref/benchmarks/cache_simulator/` (simulator reference). sha256 in `SOURCE.sha256`.
  `ref/benchmarks/__init__.py` is an empty package marker added by us.
- `src/timing_driver.cpp` is OURS (same stdin format, adds steady_clock timing of
  `SimulateEvictionPolicy`; links the unmodified port).
- Traces: decode-only streams exactly as sealed exp704 (prefill records excluded):
  granite N=638208 distinct=1262 nl=32 prior=0.2; hi N=786432 distinct=5097 nl=48 prior=8/128;
  lo N=638208 distinct=5842 nl=48 prior=8/128. Caps = sealed exp704 grids (9 each, 27 cells).
- Policies: lru lfu lfu_k lhu lru_k arc 2q lirs s3fifo sieve w_tinylfu layer_lru lcnu
  (the engine's full non-legacy list, checked against `driver --names`).
- Compiler: Apple clang 17, `-std=c++17 -O2`. Interpreter: exp650 .venv python (torch).

## Bars (binding)
- **P1 ENGINE_PARITY**: C++ hit count == upstream Python simulator hit count, exact integer,
  in all 351 (trace, cap, policy) cells; C++ run twice, bit-identical.
- **P2 SEALED_ANCHOR**: C++ LCNU hit rate == sealed exp704 LCNU `whole` rate (our older
  harness snapshot) within 1e-12 in all 27 cells.
- **P3 DEFAULT_ON_REAL_TRAFFIC**: LCNU is best or within 0.5pp of the best shipped policy
  in >= 90% of the 27 cells (>= 25/27).
- **P4 OVERHEAD**: LCNU median ns/access (3 reps, det cap and max cap) <= 1000 ns on every trace.
  Descriptive only: per-decode-token CPU cost = ns/access x layers x top_k; scan-based
  policies' cost.

## Verdict ladder
- Any P1/P2/determinism failure -> **PARITY-BREAK** (failing cells listed; upstream bug candidate).
- Else **PARITY-HOLDS:DEFAULT-CONFIRMED** if P3 passes, **PARITY-HOLDS:DEFAULT-CHALLENGED**
  (winners named per cell) if not.
- Suffix **OVERHEAD-OK** / **OVERHEAD-HIGH** from P4.

## Scope limits (stated in advance)
Tests the policy port through `SimulateEvictionPolicy` (the simulator-semantics replay path),
NOT `ExpertResidencyManager` integration (needs a CUDA build; upstream already disclosed
S3-FIFO +13 hits at 2048 slots there). No latency/throughput claim; hit rates only.
Timing measured on Mack (M4) while another CPU experiment runs; loadavg recorded.
