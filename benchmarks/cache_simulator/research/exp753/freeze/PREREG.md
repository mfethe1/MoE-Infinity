# exp753 PREREG — moei-execpath-handoff: where do the 62 engine-only ms/tok go, and can a CUDA-graph decode step exist?

- Program: STACK-1001-79990, lane 79990-tier1-7687a6bf1295 (sole owner; hermes@mack cron fire 2026-11-08T0230Z)
- UID: stack1001-contrib-exp753-moei-execpath-handoff-winnie-v1-20261108
- Host: Winnie (WSL2, driver 580.xx), GPU1 = RTX 5060 Ti 16GB (gen4 x8) — same GPU/model/config as exp746/747/752 sealed baselines
- Model: OLMoE-1B-7B-0125-Instruct (~/models), offload ~/moe-offload, policy lcnu, ratio 0.75, threads 4, gpu-route on, max_new 64, greedy, prompts.json (6 fixed prompts, sealed since exp744)
- Engine: MoE-Infinity upstream main @ 0337988 (src_orig/expert_dispatcher.cpp sha256 339b0fe4af215e27a38a4fbb15f43a8ef29bde08992f312dc3db3a4a9fa580d6) + private instrumented copy (exp753.patch). ~/moei-engine untouched; private build under /home/mfeth/exp753/src (PYTHONPATH), rebuild of moe_infinity._store only.
- $0 spend; no new models/providers/rentals/access. EPU unarmed. Model rule honored: no DeepSeek Flash anywhere in this lane's runtime/review/delegation.

## 1. Question
exp752 (sealed, ADDENDUM75): engine H arm = 93.90 ms/tok median (clean n=2), HF reference = 31.79 ms/tok (n=3) → GAP = 62.11 ms/tok of engine-only overhead that retire-by-event (R) and completion-by-query (RC) barely touched (RC closed 13.2%). exp738 GROUPED-FLAT pre-decided that batching experts does not help. BELIEFS re-rank put "exec-path handoff decomposition" top (9.415).

- Q1 (ATTRIBUTION): Within the 62 ms/tok gap, how much is GPU kernel busy time vs host-side handoff machinery (route hostfn latency, route worker CPU, exec queue wakeup, per-expert host exec, completion/retirement callbacks, caller wait), and what is the single largest per-token sub-lever?
- Q2 (GRAPH FEASIBILITY): Can a per-layer dispatch sequence (set_inputs→dispatch_experts, and isolated: pinned-alloc, cudaLaunchHostFunc) be stream-captured into a CUDA graph on this WSL2/driver/engine stack — the precondition for a graph-based decode step?
- Q3 (OBSERVER OVERHEAD): Does the env-gated timeline trace perturb end-to-end ms/tok by ≤5%?

## 2. Predictions (registered before any measurement)
- P1: HANDOFF-BOUND — decode kernel busy accounts for ≤30% of the gap; largest single sub-lever is route/completion hostfn stream latency on WSL (cf. exp747: ~522µs per cudaLaunchHostFunc round) or exec wakeup. Confidence 0.70.
- P2: Trace overhead ≤5% on both traced arms. Confidence 0.85.
- P3: CUDA-graph capture of the per-layer dispatch FAILS at cudaLaunchHostFunc or pinned-host alloc with cudaErrorStreamCaptureUnsupported/NotAllowed (or captures but replay diverges). Confidence 0.55. A positive result would be a major new direction (graph decode step).
- P4: A arm reproduces exp752 H band: median ms/tok within 93.90 ± 10% (drift band per upstream #254 contention nondeterminism).

## 3. Design
Arms (all GPU1, serial, one process per cell, quiet-gated):
- hf: HF transformers reference (hf_arm.py, byte-identical to exp752's) — gap denominator, drift sentinel.
- A: engine, UNPATCHED behavior (trace off, compute-timing off). Headline ms/tok. Binary contains the dormant tracer (env-gated; disabled path = 1 relaxed atomic load per site).
- B: engine + MOEI_EXP753_TRACE=1 (21-site host timeline, steady_clock/CLOCK_MONOTONIC ns, 40B records, 8M-slot preallocated ring, atexit JSONL dump; no CUDA calls, no locks, no allocation in hooks).
- C: B + set_overlap_compute_timing_enabled(True) via the existing engine hook (per-expert CUDA event pairs; adds EXP753_KERN_SAMPLE with kernel_duration_ns at WorkerTiming::Poll; engine-side drain/prefetcher observation left in place — part of the arm).
- G: graph_probe.py — CUDA-graph capture probes in a disposable process: (0) positive control add-graph capture+replay; (1) torch pinned alloc inside capture; (2) cudaLaunchHostFunc (ctypes, no-op callback) inside capture; (3) real per-layer set_inputs_with_invocation+dispatch_experts inside capture; (4) if (3) captures: replay×32 vs eager×32 timing + output sanity. Exact exception strings/cuda codes recorded per step.

Cells (palindromic interleave; frozen): hf_1, a_1, b_1, c_1, g_probe, c_2, b_2, a_2, hf_2.
Per cell: allquiet746.sh quiet gate (≤5400s), precell.csv env row, mon753.sh foreign-kill watcher (FLAGGED → timing excluded, parity kept — exp752 precedent), nvsamp.py 0.05s GPU util sampling, timeout 1800 (G: 1200), CUDA_VISIBLE_DEVICES=1.
Per-prompt protocol identical to exp744-752: 1-token probe then 64-token full run; decode ms/tok per prompt = 1000·(t_full−t_1tok)/63; cell value = median over 6 prompts; arm value = median over replicates.
Harness records CLOCK_MONOTONIC ns windows per full run (win_mono) — same clock as C++ steady_clock on Linux → trace↔prompt-window join.

## 4. Parity gate (G-P) — frozen from sealed exp752 structure, pre-measurement
Sealed exp752 finding (pairwise token comparison of all 12 cells): prompts 0-3 and 5 are token-identical across ALL clean engine cells (H/R/RC ×3); prompt 4 diverges at token 21 in EVERY engine arm and replicate (intrinsic baseline greedy near-tie + nondeterministic 4-thread expert accumulation order); the contaminated H_1 additionally flipped prompt 5 @31. hf arm is fully deterministic (3/3 identical).
Therefore, for every engine cell (a/b/c, FLAGGED included):
- prompts 0,1,2,3,5: exact 64/64 token match vs refs/engine_ref.json (exp752 H_1 ids).
- prompt 4: exact match of first 21 tokens; divergence at/after index 21 permitted and reported (KNOWN-BASELINE-TIE), not a quality failure.
For hf cells: exact 6/6 vs refs/hf_ref.json.
Any violation outside these bounds → PARITY FAIL → no timing verdict, patch treated as behavior-changing (BLOCKED-PATCH).

## 5. Manipulation checks (G-M)
1. Banner `exp753 mode=<ARM> trace=<0|1> timing=<on|off>` in every engine cell log.
2. B/C traces: meta line records>0, dropped==0 (ring overflow ⇒ FAIL).
3. Site coverage: sites {1..14,16..21} counts>0 in B and C; site 15 (KERN_SAMPLE) >0 in C and ==0 in B.
4. Conservation per trace: #(ROUTE_FUNC_ENQUEUE) == #(EXEC_POP) == #(EXEC_PUSH payload∈{1,2,3}); #(SETINPUTS_EXIT with expert≥0) == #(SETINPUTS_ENTER) (uniform invocation path — required for C-arm sampling).
5. C decode-window: #(KERN_SAMPLE) within 1% of #(ROUTE_FUNC_ENQUEUE) in the same windows.
6. Provenance: analyzer recomputes sha256 of all files listed in out/RUN_SHA256 and requires equality; frozen-source sha recorded in FREEZE file (git commit of prereg+patch+harness, pushed before first measurement cell).
Decode-window definition (frozen): records with ns inside a full-run win_mono window of the same cell, generations classified decode iff 1 ≤ #(ROUTE_FUNC_ENQUEUE per generation) ≤ 8 (top-6 routing; prefill routes more).

## 6. Decision rules (frozen)
- D1 ATTRIBUTION: gap = median(A cells) − median(hf cells), ms/tok. kernel_busy = Σ KERN_SAMPLE.payload over decode windows of C traces / decode tokens (decode tokens = decode generations/16) → ms/tok. ratio = kernel_busy/gap. ratio ≥ 0.5 → KERNEL-BOUND; ≤ 0.3 → HANDOFF-BOUND; else MIXED. Stage table from B traces (median spans; per-token contribution = median × per-token count: gen-level ×16, expert-level ×~96): de_cpu (3→4), hf_lat (4→5), route_q (6→7), route_cpu (7→9), wakeup_hit (EXEC_PUSH p1→EXEC_POP, per expert), wakeup_fetch (p2/p3→POP), exec_host (11→13), out_done (13→14), pend_lag (max 14−14? no: per gen COMPLETE_ZERO − last OUTPUT_DONE), wait_span (17→18), wait_tail (18→19), retire_cb lag (21 − nearest preceding 14, hostfn), completion_cb lag (20 − 19). untraced_residual = median(A) − Σ contributions − wait_span − wait_tail (python/transformers/sampling floor). Top sub-lever = largest per-token contribution; reported with share of gap.
- D2 GRAPH: positive_control OK ∧ probe3 captured ∧ replay verified → CAPTURE-OK (+replay speedup descriptive). Else CAPTURE-FAIL@(first failing step, error string, cuda code). Positive control failing → INCONCLUSIVE-ENV (probe environment broken; no feasibility claim).
- D3 OVERHEAD: for X∈{B,C}: |median(X)−median(A)|/median(A) ≤ 0.05 → OK else PERTURBS (decomposition still reported; headline ms/tok always from A).
- Exclusions: mon753 FLAGGED or precell contamination (gpu_mem>1024MB or ollama loaded) → cell timing-excluded, parity kept; RC≠0 → cell FAILED (excluded; log tail preserved). Both A cells excluded → D1/D3 INCONCLUSIVE (parity/trace/probe still reported). Both C cells excluded → D1 falls back to B-trace host decomposition with kernel_busy unavailable → INCONCLUSIVE-ATTRIBUTION (no kernel claim without C data).
- Kill criteria: build fails after 2 fix attempts → BLOCKED-BUILD; smoke (2-prompt trace+timing, post-build pre-freeze, disclosed as smoke — no timing claims) shows parity violation or crash → abort, BLOCKED-PATCH; overhead >20% → report A + qualitative decomposition only; quiet gate exhausts 5400s → cell SKIPPED-QUIET.

## 7. Consequences (pre-committed)
- HANDOFF-BOUND ∧ hf_lat/completion-cb top → strengthens event-based retirement/completion redesign (exp752 RC direction, −5.28 ms/tok) and exp747 WSL hostfn cost line; next candidate: eliminate per-layer hostfns entirely (event-poll completion + batched retirement).
- HANDOFF-BOUND ∧ wakeup/exec_host top → next candidate: exec queue redesign (batch wakeup, per-GPU single consumer).
- KERNEL-BOUND → handoff machinery is not the lever; fold into grouped-kernel line with honest bound.
- CAPTURE-OK → open graph-decode-step direction (new prereg required; replay determinism vs prompt-4 tie caveat).
- CAPTURE-FAIL@hostfn/pinned → documented precondition: per-layer path must shed cudaLaunchHostFunc+pinned alloc before graph capture is possible (architectural finding, feeds redesign spec).
- Negative/inconclusive results sealed as-is (program rule: keep negatives).

## 8. Threats to validity
- Traced arms (B/C) are not the headline; A carries ms/tok. Observer effect bounded by D3.
- C arm adds CUDA event pairs + engine-side sample drain + prefetcher observation — a compound arm; kernel_busy is the only quantity taken from it (event-measured GPU time), not wall time.
- WSL2 clock: CLOCK_MONOTONIC vs steady_clock equivalence assumed on Linux/WSL (true; both clock_gettime(CLOCK_MONOTONIC)); verified by win_mono⊇trace-span containment check in analyzer (G-M auxiliary).
- Prompt-4 baseline tie (documented §4) means strict token parity is impossible on that prompt for ANY engine arm — gate is prefix-based there, frozen pre-measurement from sealed exp752 evidence.
- Foreign GPU activity: quiet gate + mon753 + precell covariates (same machinery as exp746-752; contaminated cells timing-excluded).
- Single host/GPU/model: results are envelope-specific (RTX 5060 Ti, WSL2, OLMoE-1B-7B, lcnu 0.75); no cross-hardware generalization claimed.

## 9. Implementation & review
- Author: lane owner (this fire). Independent substantive review: read-only reviewer (gpt-sol delegation, NOT DeepSeek Flash) of patch+prereg before freeze; findings dispositioned in REVIEW753.md. Adoption/settle: next fire (coordinator dedup via STACK ledger; evidence returned in fire receipt).
- Freeze: git commit (prereg+patch+harness+refs) to mfethe1 fork branch exp651/qwen30b-results, pushed BEFORE first measurement cell; FREEZE file records commit sha + file shas.
- Raw per-cell: json, log, trace jsonl, tracemeta, util.csv, precell.csv, FLAGGED, RUN_SHA256, ENV.txt, verdict.txt — all retained and fetched to Mack at settle.

## 10. Pre-data amendments (2026-11-08T1545Z, BEFORE any measurement cell)

Review-driven precision fixes (SUB2-out.md / SUB3-out.md, independent reviewer
`pi --print --provider mimo --no-tools` — actual instrument; §9's "gpt-sol"
was not available and the substitution is recorded in the 04:50Z receipt).
No measurement data exists yet (out/ is empty); these amendments make the
frozen instrument exactly computable. [SC] = scientific consequence.

1. **Exact model constants** [SC]: OLMoE-1B-7B-0125-Instruct config.json =
   num_hidden_layers=16, num_experts=64, num_experts_per_tok=8 (top-8).
   - decode tokens: `toks = decode_gens / 16`, generations namespaced per
     prompt window; decode classification bound frozen as
     1 ≤ #(ROUTE_FUNC_ENQUEUE per generation) ≤ 8 (comment corrected from
     "top-6" to "top-8"; numeric bound unchanged).
   - expert-level events per decoded token: MEASURED from the traces
     (per-traffic-class counts / toks, recorded in the verdict as
     `counts_per_token`); config ceiling = 16 × 8 = 128 (replaces "×~96").
2. **D1 stage spans** [SC]: exactly the §6 site pairs — wakeup_hit =
   EXEC_PUSH(p1)→EXEC_POP, wakeup_fetch = EXEC_PUSH(p2/3)→EXEC_POP,
   exec_host = EXEC_POP(11)→EXEC_FWD_RETURN(13), out_done =
   EXEC_FWD_RETURN(13)→OUTPUT_DONE(14) (per-token count = number of such
   pairs), pend_lag = COMPLETE_ZERO − LAST OUTPUT_DONE per gen,
   retire_cb_lag = RETCB(21) − nearest preceding OUTPUT_DONE(14),
   completion_cb_lag = COMPLETION_CB(20) − WAIT_EXIT(19).
3. **untraced_residual** [SC]: = median(A) − Σ contributions − wait_span −
   wait_tail where Σ contributions INCLUDES retire_cb_lag + completion_cb_lag.
4. **Parity gate**: every row must have n_new==64 and out length 64;
   rows keyed by prompt id; exactly 6 rows (ids 0..5) asserted. Parity FAIL →
   D1/D3 suppressed to PARITY-FAIL.
   - prompt 4 engine gate: `refs/engine_ref.json` (source: exp752
     `out/H_1.json`, provenance in ref header) stores exactly the frozen
     21-token-ID divergence prefix for prompt 4; exp753 forces 64 new
     tokens (`min_new_tokens=64`), so prompt 4 passes iff
     `n_new==64 AND len(out_ids)==64 AND out_ids[:21] == engine_ref[4]`.
     Strict prompts and all hf rows: full equality vs their ref. Truncated
     or early-EOS reps must NOT pass parity (they cannot shrink the
     ms/tok denominator).
5. **D1 gap consequences**: gap ≤ 0 → INCONCLUSIVE-gap-nonpositive (never
   MIXED); no clean A/HF cells → INCONCLUSIVE-no-clean-cells.
6. **P4 consequence**: P4 violated (A outside 93.90 ±10%) → DRIFT; D1/§7
   attribution claims SUSPENDED (reported descriptive with
   ";SUSPENDED-P4-DRIFT"); rerun required before attribution claims.
7. **G-M additions**: (a) TRACE-SPAN containment — per full-run window the
   first/last in-window trace record must lie within 15% of the window edges
   (silent-stop detector; violation = G-M fail, flag TRACE-SPAN:<cell>);
   (b) KERN-COVERAGE runs on ALL C traces — FLAGGED excludes TIMING only;
   (c) generation keys namespaced per prompt window (raw counter reuse across
   windows flagged GEN-COUNTER-RESET-SEEN); (d) analyzer asserts its site-id
   map against infra753.inc enum Exp753Site (1..21) and REFUSES to analyze on
   mismatch (hard-fail; unverified parse → MANIP flag).
8. **Row/cell timing** [SC]: t_full − t_1tok ≤ 0 → row flagged
   DECODE-DELTA-NONPOSITIVE, excluded from cell medians; cell with <3 valid
   rows → INVALID-ROWS. t_1tok_s >±20% from cell median → flag
   PROBE-PREFILL-DRIFT (descriptive). Both probe and full CLOCK_MONOTONIC
   windows recorded per row (win_mono_probe / win_mono). FLAGGED cells
   timing-excluded with parity kept; FAILED (RC≠0) cells excluded entirely.
9. **G cell execution** [SC]: each probe in its own disposable subprocess
   (fresh CUDA context). After any FAILED capture no sync/wait/replay runs;
   child records and exits immediately. CAPTURE-OK requires positive control
   OK AND dispatch capture AND replay-output equivalence (32 replay vs 32
   eager generations, shapes equal, allclose max-abs ≤ 1e-4, all finite) —
   replay verification is measured output equality, not a null check.
   cudaLaunchHostFunc CAPTURED requires launch rc==0 AND replay callback
   fired ≥1 (rc recorded in all paths). Exit codes: 0 = outcomes recorded
   (incl. genuine CAPTURE-FAIL), 3 = positive control FAIL (→
   INCONCLUSIVE-ENV), 2 = probe crash, 1 = result missing.
10. **Precell covariate → FLAGGED triggers** (pre-committed): pre-start GPU
    memory > 1024 MiB OR ollama loaded ≠ 0 OR 1-min loadavg ≥ 8 OR
    Runner.Worker ≥ 1 OR foreign GPU compute-apps ≥ 1 (baseline measured 0;
    the 345 MiB GPU1 resident is driver overhead, no compute contexts).
    In-run monitoring (mon753/nvsamp) unchanged.
11. **Trace-file naming (R1)**: production writes `<cid>.trace.jsonl`; the
    analyzer keys the base id `<cid>` accordingly (a plain `<cid>.trace` key
    silently no-op'd the whole decomposition — caught in independent review).
12. **TF32 pinned OFF (R6, ERRATUM-752-TR32)**: both harnesses set
    `torch.backends.cuda.matmul.allow_tf32 = cudnn.allow_tf32 = False` before
    any generation and record the readback per cell json (`allow_tf32`);
    analyzer raises `MANIP:TF32-ENABLED` if either reads True.
13. **Pairing is order-preserving (R9)**: all FWD_RETURN→OUTPUT_DONE /
    EXEC_PUSH→EXEC_POP style pairs use monotone matching (each source event
    matched to the first UNUSED later event), correct for interleaved expert
    events; the first-b-after-a rule mispaired concurrent experts.
14. **Full-token rows only (R10)**: rows with `n_new != 64` or
    `len(out_ids) != 64` are excluded from ALL timing medians with an
    `INVALID-ROW-NNEW` flag and cannot pass parity (they represent early-EOS
    repetitions).
15. **completion_cb_lag direction + no double count**: both
    COMPLETION_CB(20)−WAIT_EXIT(19) orders are computed; if the callback sits
    INSIDE the wait window the lag is reported but flagged
    `COMPL-LAG-IN-WAIT` and excluded from the untraced_residual chain (it is
    already covered by wait_span). untraced_residual is reported per clean A
    cell (= cell med − Σ contributions − wait_span − wait_tail) plus the
    median across clean cells.
16. **graph_probe robustness (R2/R5/R13/R14)**: nested step records are
    flattened recursively; missing/undecodable g_probe.json yields
    INCONCLUSIVE-NO-G-CELL + MANIP flag (never a crash); exit-code contract:
    0 = outcomes recorded (incl. genuine CAPTURE-FAIL), 1 = result
    missing/undecodable, 2 = any nonzero child rc (crash, incl. negative
    returncodes), 3 = positive control FAIL; row schema mismatches are
    flagged (ROW-SCHEMA), never KeyError. Refs are keyed `out_ids`
    (verified live: 6 rows [64,64,64,64,21,64]; engine p4 = the frozen
    21-ID divergence prefix from exp752 `out/H_1.json`).
17. **Invocation-path activation (smoke finding 2026-11-08)**: the smoke run
    (SMOKE-FAIL: kern15=0, si_exitid=0 with 175,529 records otherwise
    healthy) proved the compute-timing invocation path never engaged: the
    executor chooses SetInputsWithInvocation only when
    `_dispatcher_timing_ready(prefetcher)` sees the prefetcher's overlap caps,
    which are built only for `overlap_prefetch_policy != "off"` (default off);
    without invocation ids no compute-timing pairs are acquired
    (expert_dispatcher.cpp: `timing_enabled && args.invocation_id != 0`) and
    EXP753_KERN_SAMPLE never retires. The harness (engine_arm753.py) now
    activates the gate uniformly on ALL engine arms by shadowing
    `ExpertExecutor._dispatcher_timing_ready`; source-verified
    SetInputsWithInvocation == SetInputs + counter + one tracer record
    (expert_dispatcher.cpp 3188-3198) — observation-equivalent, arms still
    differ only in trace/timing toggles (the pair path itself remains gated on
    the per-arm `--timing` flag). Provenance recorded per cell json
    (`invocation_gate_flip`). The smoke's `si_enter==si_exitid (e>=0)` check
    exercises exactly this path.

Amendment author: lane owner (this fire), implementing the independent
review's findings; the amended instrument is re-reviewed by the same
independent reviewer before freeze (finding closure required, BLOCK clears
only on all P0/P1 dispositioned).
