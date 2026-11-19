# RESULTS-M1 — exp827: all-resident reference vs streaming engine (PIVOT-A)

Run 2026-11-19T04:19-04:44Z, Winnie GPU1 (16GB), unit exp827-m1, sequence ref,eng x3.
Rounds 1-2 of each mode were killed by the quiet gate (GPU1 util 42-52%: Windows-side
Ollama MiMo reload mid-window despite paused re-summon cron). Verdict computed from clean
round 3 only (n=3 blocks per shape, spread 0.6-5.8%). Harness: m1_reference.py sha
371111112c974688 (FREEZE-827.json), left-padded b8, min_new_tokens=128 (engine path
truncates at EOS: 918-919 actual tokens - actual-token denominators used throughout).

## Numbers (script-computed, pasted verbatim from m1_analysis)
- REF (bf16 resident, plain HF): b1 [31.23, 31.39, 31.63] median 31.39 tok/s; b8 [87.7, 88.11, 88.25] median 88.11 tok/s
- ENG (moe_infinity offload 0.50): b1 [12.6, 13.28, 13.36] median 13.28 tok/s
- P1: REF_b1/ENG_b1 = 31.39/13.28 = 2.36x  (threshold >=1.5) -> PIVOT-A
- P3: REF b8 median 88.11 tok/s = 6.63x engine b1 (headroom for batch repair)
- eng b1 spread 5.8%; ref b1 1.3%; ref b8 0.6%

## Verdict (per MYTHOS-ADJUDICATION-20261118.md §2)
PIVOT-A. Expert-offload streaming taxes b1 decode 2.36x vs the same model resident in
bf16 on the SAME card (the 7B-active MoE fits: 13.8GB loaded after the Windows VRAM floor
dropped post-Ollama-unload). Consequences, in adjudicator's order:
1. Fit-able models: quantized full residency is the near-free competitor - score it first.
2. >VRAM models: streaming/offload remains the lane; RAM-first thesis must be benchmarked
   on a model >= 2x VRAM (Qwen30B-A3B-class), not OLMoE-1B-7B.
3. M2 dispatcher counters (b1) next: where does the 2.36x go (dispatch events vs expert
   misses vs PCIe)? Decides in-engine dispatch elimination (#7).
4. Engine b1 13.28 tok/s cross-checks exp825 fast-phase 11.2-11.3 (different protocol).

## Known harness logging flaw (non-blocking)
m1_run.status recorded exit=0 for processes that died on the quiet-gate AssertionError;
err files + JSONs are ground truth. Not fixed in-sequence (frozen manifest).

## Artifacts (full shas)
- m1-ref.json  d6febb70624f23e12eec951b0be0e61c3f3bb886faed05acdbdd42f358144510
- m1-eng.json  f0e8cc2e3a9f7acec4d0c037291d5d05d6382a4dcfcf852feee621a21fe10772
