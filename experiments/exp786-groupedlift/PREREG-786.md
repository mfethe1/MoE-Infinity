# PREREG-786 — grouped-decode pro6000 kernels on consumer sm_120 (gate lift A/B)

**Registered:** 2026-11-11 (pre-launch, frozen before run)
**Question:** Does enabling the RTX-PRO-6000-tuned grouped-decode expert kernels on
consumer sm_120 (2x RTX 5060 Ti) via the shipped `MOE_INFINITY_UNVALIDATED_HW=1`
escape hatch change batch-1 decode throughput vs the default per-expert path, at
ratio 0.75 (saturated) and 0.25 (miss-heavy)?

**Lever:** `moe_infinity/utils/hw_profile.py:supports(RTX_PRO_6000)` and its C++ twin
`extensions/kernel/hw_profile.h:Supports(Gate::kRtxPro6000)` both return True when
`MOE_INFINITY_UNVALIDATED_HW=1` (upstream-documented "for re-tuning on another card").
`model_offload.py` then calls `expert_dispatcher.set_grouped_decode(True, top_k, kind)`,
switching expert FFN decode from per-expert GEMM launches to grouped split-K kernels
(`extensions/kernel/grouped_moe_decode_pro6000.cu`, tuned for 188 SM / 128 MiB L2).
No source patch, no rebuild: unmodified src753 build (HEAD b7f6ca4, _store f54e5756).

**Design:** identical skeleton to exp785. 8 cells C/S x 0.75/0.25 x a/b, GPU1,
threads=4, gpu-route on, lcnu, bf16 store (~/moe-offload), OLMoE-1B-7B-0125-Instruct,
24 prompts x 32 new tokens, 2 reps interleaved a/b. Engine sets the env BEFORE
importing moe_infinity (native read-once static + Python lru_cache require it);
banner readback `grouped_decode_effective` must be True in every S cell, False in
every C cell, else rc9.

**Pre-freeze probes (8 prompts x 24 tok, not sealed data):**
- ctl @0.75 (uhw off): 9.237 tok/s; uhw @0.75: 9.393 tok/s (+1.7%, near noise)
- ctl @0.25: 9.735 tok/s; uhw @0.25: 11.199 tok/s (+15.0%; every prompt faster)
- misses unchanged (~2390 vs ~2340/prompt @0.25) -> routing traffic same; the
  change is the expert-compute dispatch path.
- kernels run cleanly on sm_120 (same compute capability 12.0; no crash, no assert).

**Prediction:** d25 in +8%..+20% (MILD-POS); d75 within +-5% (NO-MOVE regime-wise).
Overall expected rc=2 MILD-POS. Alternative outcomes: rc3 if probe gain was noise;
rc4 if grouped kernels regress under harness-length runs (workspace/tile-table
mismatch on 36 SM / 32 MiB L2).

**Verdict map (analyze786.py, frozen):** 1 MAJOR-POS (any regime >= +0.50) /
2 MILD-POS (>= +0.10) / 3 NO-MOVE (both |d| < 0.10) / 4 REGRESSION (any <= -0.10) /
9 DATA-FAIL. Determinism gate: per-config (cid[:3]) rep a/b out_sha multiset equality.
Cross-arm sha divergence ALLOWED (different kernels, numeric differences) — never
a failure. Banner gate: grouped_decode_effective must match arm.

**Mechanism discriminator:** misses and routing deltas should be ~unchanged (same
policy, same routing); if tok/s moves while misses do not, the effect is compute
dispatch path (grouped single launch vs per-expert loop), consistent with the
dispatch-latency wall (exp783/784/785).

**Limitations:** probe of grouped_act_kind returned None (MoE object exposes no
.config); the native dispatcher performs its own activation classification at
set_grouped_decode — kernels executed and completed, implying a supported activation
(OLMoE is plain SiLU). Env also lifts the gptoss_mxfp4_pro6000 gate, inert for
OLMoE (expert type != 6). Tile tables remain pro6000-tuned; any win here is a
LOWER BOUND on a properly retuned consumer-sm table, not the ceiling.
