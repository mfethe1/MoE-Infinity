# Batched-decode unblocking: root cause, minimal fix, first test battery (exp825 candidate)

Date 2026-11-18. Reviewer: Mythos 5.2. Source: Mack checkout
`/Users/mfethe/warp-work/moei-granite3b-rebuilt` @ `df3b60b81f2b77277802d10a7b8b0286e08dce81`.
Nothing in the checkout was modified; this file is the only write.

Method note: besides Read/Grep/Glob I used read-only `git` commands (`git show`,
`git diff --stat`, `git grep <rev>`, `git merge-base`) to read Winnie's commit
`0337988` and exp810's `be6e17b` out of the local object database. Without that the
drift section could not be written. No network, no checkout mutation.

Citation convention: `path:line` means Mack HEAD unless prefixed `@0337988:`.
"NOT IN CHECKOUT" marks code I could not read (HF `modeling_olmoe.py`, HF
`generation/utils.py`, and the whole `moe_store` package).

---

## 1. Executive summary

1. **exp810's diagnosis is half right.** The crash is a `position_ids` device mismatch, but the wrapper re-derives nothing: on the crashing path `MoE.generate()` is one passthrough line (`moe_infinity/entrypoints/big_modeling.py:1337-1340`). Any re-derivation is inside HF `generate()` (NOT IN CHECKOUT).
2. **Leading cause (H1, inferred, not observed).** The engine moves tensors to the GPU only as arguments of hooked submodules (`moe_infinity/runtime/model_offload.py:2488-2493`, `:2516-2524`). `input_ids` enters `embed_tokens` and is moved; a CPU `position_ids` goes straight to the un-hooked rotary embedding and meets GPU hidden states at `modeling_olmoe.py:102`.
3. **Second, silent defect.** At batch 1 the native engine discards every kwarg, mask included (`big_modeling.py:1236-1242`, `:1354`, `:1370-1373`); a padded batch-1 call feeds pads as prompt. The exp810 candidate does not fix this.
4. **Source contradicts one receipt line.** `EXP-810.md:16` says batch 1 crashes with a mask; per source batch 1 on the native engine never reaches that site. The sealed traceback must settle this before launch (Q1).
5. **Three lineages, one plumbing.** Mack HEAD, Winnie `0337988` and exp810's `be6e17b` are distinct commits (HEAD/`0337988` merge-base `dc19d78`), but `big_modeling.py`, `serving/`, `engine/`, `boundary/` and `utils/arguments.py` diff empty. The Python fix applies unchanged.
6. **Grouped decode is absent at Mack HEAD** and hardware-gated to the RTX PRO 6000 on the Winnie side (`@0337988:moe_infinity/runtime/grouped_moe_pro6000.py:22-26`, `@0337988:moe_infinity/utils/hw_profile.py:14-16`). It never sees mask or position_ids; no change needed there.
7. **Minimal fix:** about 25 lines in `big_modeling.py` behind `MOE_GENERATE_ALIGN_INPUTS=1`, default off. Aligns tensor kwargs to the embedding device on the HF path and stops batch 1 from silently dropping a real mask. Bare-ids single-stream runs no new code.
8. **The amortization projection is at risk independently of the crash.** The dispatcher treats any multi-token step as prefill (`core/parallel/expert_dispatcher.cpp:1258-1260`, `:1518-1520`, `:1659-1666`), and batching also swaps the native loop for the HF loop. The battery separates these.
9. **exp825 shape:** stage 0 reads sealed tracebacks (no GPU); stage 1 is a five-arm crash smoke; stage 2 is a four-arm ABAB battery with battery-local agreement floors and a teacher-forced logit gate. Do not freeze before exp824 reports.

---

## 2. Plumbing map

### 2.1 Entry points and what each does with mask / position_ids

| #   | Site                                                             | What happens to `attention_mask` / `position_ids`                                                                                                     |
| --- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1  | `big_modeling.py:1177` `MoE.generate(self, input_ids, **kwargs)` | Accepted only as opaque `**kwargs`.                                                                                                                   |
| P2  | `big_modeling.py:1236-1242` `native_for_call`                    | True when `use_native_engine`, engine exists, `input_ids.ndim == 2`, `shape[0] == 1`. Kwargs are not consulted.                                       |
| P3  | `big_modeling.py:1337-1340` HF path                              | `self.model.generate(input_ids, **kwargs)`. Passthrough, no device handling. Reached for batch > 1, or when the native engine is off.                 |
| P4  | `big_modeling.py:1354` native path                               | `prompt_token_ids = [int(t) for t in input_ids[0].tolist()]`. Mask and position_ids are **dropped**; pads become prompt tokens.                       |
| P5  | `big_modeling.py:1363-1368`                                      | `SamplingParams` carries temperature/top_p/top_k/max_tokens only. `min_new_tokens`, `streamer`, `pad_token_id` are dropped on the native path too.    |
| P6  | `big_modeling.py:806-810` `_native_model_forward`                | Rebuilds `input_tensor` from a Python list and moves it to `_resolve_native_input_device()`.                                                          |
| P7  | `big_modeling.py:825-835` non-paged branch                       | Passes only `use_cache` / `past_key_values`. HF derives `position_ids` itself, on the embedding device. This is why bare ids work.                    |
| P8  | `big_modeling.py:840-850` paged branch                           | Builds `position_ids` on `input_tensor.device`, from `seq_lens[0]` only (single-sequence assumption). Not reached for OLMoE, see 2.3.                 |
| P9  | `big_modeling.py:947-959` `_native_model_forward_rich`           | The only wrapper site that explicitly does `.to(input_tensor.device)` on mask and position_ids. It is the in-tree precedent for the fix. DFlash only. |
| P10 | `big_modeling.py:1536-1550` `MoE.forward`                        | `self.model(input_ids, *args, **kwargs)`. Passthrough, same hazard as P3.                                                                             |
| P11 | `big_modeling.py:1268-1317` DFlash batch > 1                     | Reads the mask for prompt lengths, forwards it to the speculator. Unaffected.                                                                         |
| P12 | `serving/model_runner.py:384-390`, `:412-423`                    | Serving path builds `input_ids`, `position_ids`, `attention_mask` all on `self.device`. Correct by construction.                                      |

### 2.2 The device-movement mechanism (why only some tensors get moved)

- Per-stage input hooks. `setup_archer_hooks` registers `_pre_forward_input_hook`
  on each topology stage; it runs `copy_args_to_device` and `copy_kwargs_to_device`
  on that module's inputs (`model_offload.py:2488-2493`, registration `:2516-2524`).
  Topology stages are built only from named parameters and buffers present in the
  checkpoint map (`model_offload.py:2334-2337`, `:2396-2399`).
- Per-module hooks. `_register_hooks_recursively` registers a pre-hook on every
  module that moves the module's own non-offloaded params and buffers to the last
  visible GPU (`model_offload.py:2976-2980`, `:2990-2994`). It never touches `args`
  or `kwargs` (`:2973` takes them, the body ignores them).
- The helpers move tensors only one level deep and mutate the dict in place
  (`moe_infinity/utils/arguments.py:9-22`, `:25-34`).
- Consequence. A tensor is moved to the GPU only if it is an argument of a hooked
  stage. `input_ids` is (via `embed_tokens`). `position_ids` is consumed by the
  rotary embedding, a module with one non-persistent buffer and no checkpoint
  tensor, so it is not a topology stage and receives no input hook. Its buffer is
  moved to the GPU by the per-module hook; its argument is not.
  The claim "rotary has no stage hook" is inferred from `get_topology` plus the
  standard HF layout; it is not observed (HF code NOT IN CHECKOUT).

### 2.3 Which attention path OLMoE actually runs

- The engine swaps `OlmoeAttention` for `OlmoePagedAttention` from `moe_store`
  (`moe_infinity/boundary/transformers_model_overrides.py:92-97`).
- `MoE._get_paged_attention_classes` only recognises the two DeepSeek shims
  (`big_modeling.py:1076-1080`), so in `MoE.generate()` OLMoE always takes the
  non-paged branch. Confirmed by sealed stacks: `MoE._native_model_forward
(big_modeling.py:854)` then `OlmoePagedAttention.forward
(moe_store/wrappers/olmoe_paged_attention.py:108)` then `OlmoeAttention.forward
(modeling_olmoe.py:238)` in `experiments/exp771-func-cpu/sealed771/PY_LGC.pyspy`.
- So in `generate()`, KV history is the HF cache, and the shim falls through to HF
  attention. How the shim forwards `attention_mask` on that fall-through is NOT IN
  CHECKOUT (Q3).
- The serving runner uses a wider shim list that does include `OlmoePagedAttention`
  (`serving/model_runner.py:86-95`). The two paths disagree about OLMoE on purpose.

### 2.4 Expert-offload worker handoff

- `_configure_hook` creates one tracer entry per batch row and hands the list to
  every expert layer (`big_modeling.py:1127-1132`). Batch-aware already.
- The executor passes `hidden_states`, `router_mask`, `router_weights` to the
  dispatcher (`moe_infinity/distributed/expert_executor.py:649-657`). No mask or
  position_ids cross this boundary. Nothing to change here for the crash.
- The handoff is where padding leaks: rows are flattened to tokens before dispatch,
  and pad positions are routed like real tokens. The flattening is in
  `SyncOlmoeMoEBlock` (`moe_store/wrappers/olmoe.py`, NOT IN CHECKOUT; frames at
  lines 39-64 appear in the exp771 stacks).
- The dispatcher keys its behaviour on token count, not on phase:
  `batch_size = hidden_states_.size(0)` (`core/parallel/expert_dispatcher.cpp:1160`,
  `:1507`, `:1639`); `batch_size > 1` is commented "only for prefill" (`:1258-1260`);
  the input is gathered with a per-expert token mask when `batch_size != 1`
  (`:1517-1520`); the output is scattered with `nonzero` + `index_add_` (`:1659-1666`).

### 2.5 Grouped-decode path (Winnie side only)

- Flag read in Python: `@0337988:moe_infinity/runtime/grouped_moe_pro6000.py:22-26`
  (`MOE_GROUPED_DECODE` default `"1"`, `"0"` disables, then `supports(RTX_PRO_6000)`).
- Wired at engine init: `@0337988:moe_infinity/runtime/model_offload.py:1554-1565`.
- Flag read in C++: `@0337988:core/parallel/expert_dispatcher.cpp:368-369`; per-device
  hardware check `:373`; eligibility `:1811-1826`; token cap `:1841-1842`.
- Inputs are `hidden_states_`, `router_mask_`, `router_weight_` (`@0337988:...cpp:1977`).
  The grouped path does not see mask or position_ids. **No change needed there for
  the crash.**
- None of these files exist at Mack HEAD (`git diff --stat 0337988 HEAD` lists
  `grouped_moe_pro6000.py`, `grouped_moe_decode_pro6000.cu/.h`, `kernel/router.py`,
  `fused_router.cu` as deleted relative to `0337988`).

### 2.6 Sites that must change

| Site                        | Change                                                                                   | Needed for                                 |
| --------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------ |
| `big_modeling.py:1337-1340` | Align `input_ids` and tensor kwargs to the embedding device before the HF call           | The crash                                  |
| `big_modeling.py:1236-1242` | Do not take the native path when a mask with zeros or explicit `position_ids` is present | Silent pad ingestion at batch 1            |
| `big_modeling.py:1548-1550` | Same alignment for `MoE.forward`                                                         | Teacher-forced equivalence probe in exp825 |

No change in `model_offload.py`, `engine_ops.py`, `serving/engine.py`,
`expert_executor.py`, the dispatcher, or any kernel.

---

## 3. Ranked root-cause hypotheses

### H1 (most likely). Caller-side CPU mask, HF derives CPU position_ids, no hook moves them

Chain:

1. The known-good harness lineage calls `generate()` with bare ids
   (`experiments/exp824-aa-estimator/EXP-824.md:79-80`: "known-good engine
   invocation: `generate()` with bare input IDs only"). Tokenizer output on CPU
   works on that path because P6 moves it.
2. exp810 added `apply_chat_template(padding=True)` (`EXP-810.md:5`). If the
   resulting dict was passed with the same device handling, the mask is on CPU.
3. Batch > 1 takes P3. HF `generate()` derives `position_ids` from the mask, on the
   mask's device (HF behaviour, NOT IN CHECKOUT, stated from memory of the library).
4. `embed_tokens` input hook moves `input_ids` to the GPU (2.2). Hidden states are
   on `cuda:0`. `position_ids` stays on CPU and reaches the rotary embedding.
5. Crash at `modeling_olmoe.py:102`, "cuda:0 and cpu" (`EXP-810.md:10-11`).

Fit: explains attempt-2 5/5 (`EXP-810.md:14`) and "bare ids ran clean" (`:16`).
Does not by itself explain attempt-3 or the B1 statement. See H2 and H4.

### H2. HF `generate()` re-derives position_ids from the mask and ignores the caller's tensor

exp810 attempt-3 passed CUDA `position_ids` and still crashed at the same site
(`EXP-810.md:15`). The wrapper cannot be the re-deriver (P3 is one line). If the
mask was still on CPU in attempt-3, then either HF overwrote the caller's
`position_ids` with a mask-derived CPU tensor, or the caller's tensor was built
from a CPU mask and moved incompletely. Both reduce to "mask on CPU".
Evidence available here: none beyond the receipt. Evidence needed: the attempt-3
script from the seal (`EXP-810.md:33`, sha256 begins `78489eac`).

### H3. Hidden states on CPU instead (inverse mismatch)

`position_ids` on GPU, embedding output on CPU. Would need `embed_tokens` to run
un-hooked or the post-hook to move its output to CPU
(`model_offload.py:3062-3071` moves outputs to `device_list[0]` when a module has
non-offloaded params). `embed_tokens.weight` is registered (`:2458-2463`), so
`param_not_offload` is empty and no move occurs. Unlikely. Ruled out further by
the fact that bare-ids decoding works through the same embedding.

### H4. The crash is not on the path exp810 assumed (B1 contradiction)

`EXP-810.md:16` says batch 1 crashes when a mask is passed. With the native engine
on, batch 1 goes P2 → P4 → P6 → P7 and never touches a caller mask. Candidates:

- the exp810 harness config had `use_native_engine` false
  (`moe_infinity/utils/config.py:95`; effect at `big_modeling.py:419-429`), so B1
  took P3;
- the B1 arm passed a tensor that was not `[1, L]`;
- the "B1" label covered a different call shape.
  exp771 stacks show the native path active for bare batch-1 calls at that time
  (`big_modeling.py:1370` frame in `PY_LGC.pyspy`), so the first candidate would
  have to be a config difference between exp771/exp809 and exp810.
  This is not a competing root cause for the batch > 1 crash; it is a hole in the
  receipt that decides whether the fix needs the batch-1 guard to reproduce exp810's
  B1 result at all.

### H5. `get_device()` silent CPU fallback

`moe_infinity/utils/device.py:25-30` returns `"cpu"` for an out-of-range index
instead of raising. Used at `model_offload.py:2979`, `:2993`, `:3067`. With
`device_count() >= 1` the argument is always valid. Not the cause; a latent hazard.

### What the exp810 candidate fixes and what it does not

"Keep position_ids/mask on the input device through the wrapper's forward plumbing"
(`EXP-810.md:27`):

| Fixes                                                          | Does not fix                                                                         |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| H1: aligning the mask means HF derives position_ids on the GPU | P4: batch-1 native path still discards the mask and feeds pads as prompt             |
| H2: a GPU mask makes any HF re-derivation land on the GPU      | H4: cannot be evaluated until the sealed traceback is read                           |
| Caller-supplied CPU position_ids (aligned directly)            | Whether the `moe_store` attention shim honours the padding mask on fall-through (Q3) |
|                                                                | Dispatcher treating multi-token decode as prefill (2.4)                              |
|                                                                | Native-loop vs HF-loop confound in any batch-vs-single comparison                    |
|                                                                | P5: `min_new_tokens` and `streamer` ignored at batch 1 on the native path            |

One wording correction to the candidate: "input device" must mean the embedding
device, not the caller's `input_ids.device`. The caller's ids are routinely on CPU
(the native path tolerates that). Aligning to a CPU `input_ids` would keep the crash.

---

## 4. Minimal fix design

### 4.1 Diff (design, not applied)

One file, `moe_infinity/entrypoints/big_modeling.py`. Flag
`MOE_GENERATE_ALIGN_INPUTS`, default off, read per call.

```python
# module level
def _align_inputs_enabled() -> bool:
    return os.environ.get("MOE_GENERATE_ALIGN_INPUTS", "0") == "1"

# method on MoE
def _align_generate_inputs(self, input_ids, kwargs):
    device = self._resolve_native_input_device()
    moved = {
        key: value.to(device) if isinstance(value, torch.Tensor) else value
        for key, value in kwargs.items()
    }
    return input_ids.to(device), moved
```

Change A, HF path (`:1337-1340`):

```python
            self._configure_hook(input_ids)
            self.model.eval()
            if _align_inputs_enabled():
                input_ids, kwargs = self._align_generate_inputs(input_ids, kwargs)
            with torch.no_grad():
                return self.model.generate(input_ids, **kwargs)
```

Change B, native-path guard (after `:1242`):

```python
        if native_for_call and _align_inputs_enabled():
            mask = kwargs.get("attention_mask")
            if kwargs.get("position_ids") is not None or (
                mask is not None and not bool(mask.to(torch.bool).all())
            ):
                native_for_call = False
```

Change C, `MoE.forward` (`:1548-1550`): same two-line alignment before
`self.model(...)`.

`_resolve_native_input_device` already exists and already encodes the right answer
for multi-GPU (`big_modeling.py:770-804`). `os` and `torch` are already imported.

### 4.2 Why this shape

- **Smallest surface.** No hook is added. A top-level forward pre-hook with
  `with_kwargs=True` would also catch tensors HF creates internally, but it would
  run on every forward of every call shape, including the measured single-stream
  path, and so could not be claimed behaviour-neutral without measuring.
- **Opt-in, no silent change.** With the flag unset the code path is unchanged
  apart from one `os.environ.get` per HF-path call. Bare-ids batch-1 calls never
  reach change A and hit change B only as a false `and`.
- **Precedent.** The alignment is the same operation already shipped at
  `big_modeling.py:952-959` for the DFlash rich path. RMSNorm fusion shipped
  opt-in and eval-graded (`experiments/exp814-fused-rmsnorm/EXP-814.md`,
  `experiments/exp815-faithful-fusion/EXP-815.md`).
- **Change B routes rather than strips.** Stripping pads and continuing natively
  would be faster for batch 1 but adds a left/right-padding decision and a second
  code path to test. Routing a masked batch-1 call to the HF path is one branch and
  makes B1-with-mask behave like B8-with-mask, which is what the battery compares.
  An all-ones mask at batch 1 stays native, so existing callers that pass a
  trivial mask keep their path.

### 4.3 Single-stream equivalence

- Flag off: bit-identical code path to today.
- Flag on, bare ids, batch 1: change A not reached, change B false. Same path.
- Flag on, all-ones mask, batch 1: stays native, mask still discarded, as today.
- Flag on, padded or explicit-position batch 1: moves from native loop to HF loop.
  Outputs are expected to agree only up to greedy near-tie flips. This is a
  behaviour change, intentionally confined behind the flag.
- Independent of this fix, expert accumulation order is not fixed:
  `index_add_` from concurrent exec streams into one accumulator
  (`core/parallel/expert_dispatcher.cpp:1659-1666`; grouped variant
  `@0337988:...cpp:1699-1712`). This is the mechanism behind the standing
  `grouped-decode-determinism-is-expert-order` note. The fix neither causes nor cures it.

### 4.4 Verification the implementer owes before any GPU battery

1. Unit test, CPU-only, stub model: with the flag on, a CPU mask and CPU
   position_ids arrive at `self.model.generate` on the resolved device; with the
   flag off they arrive untouched. Pattern: `tests/python/unit/test_olmoe_return_contract.py`.
2. Unit test: flag on, batch 1, mask with a zero → `native_engine.generate` not
   called. Flag on, batch 1, all-ones mask → called. Flag off → called.
3. Existing suite unchanged: `tests/python/dflash/test_rich_batch_forward.py`,
   `tests/python/serving/test_model_runner.py`.

---

## 5. Test battery design (exp825 candidate)

Status of everything below: **design**. No number in this section is a measurement.

### 5.1 Preconditions (all must hold before freeze)

- exp824 has reported. Its estimator is "in flight"
  (`experiments/exp824-aa-estimator/EXP-824.md:3`). If exp824 G2 fails (any battery
  with CI excluding 0, `EXP-824.md:50-52`), exp825 walls are reported descriptively
  and wall gates W1/W2 are struck before launch, not after.
- Q1 answered from the exp810 seal (stage 0 below).
- The patch is applied on Winnie's tree as a recorded diff with its sha256 in the
  freeze manifest, and the unit tests in 4.4 pass there.

### 5.2 Stage 0 — sealed-evidence read (no GPU, no wall budget)

From `/home/mfeth/exp810-seal.tgz` (`EXP-810.md:33`):

- S0a: full traceback of one batch > 1 arm. Record whether the frame above HF is
  `big_modeling.py:1340`.
- S0b: full traceback of the B1 arm. Record whether it passes through `:1340` or `:854`.
- S0c: the harness lines that build and move `input_ids`, `attention_mask`,
  `position_ids`, and the `use_native_engine` value.

Outcome table, fixed in advance:

| S0a frame   | S0b frame | Reading                                                                             |
| ----------- | --------- | ----------------------------------------------------------------------------------- |
| `:1340`     | `:1340`   | H1/H2 confirmed; exp810 ran with native engine off or B1 was not `[1, L]`. Proceed. |
| `:1340`     | `:854`    | Source analysis in this report is wrong somewhere. **Stop**, do not launch.         |
| not `:1340` | any       | H1 refuted. **Stop.**                                                               |

### 5.3 Stage 1 — crash smoke (GPU 1, one fresh process, not a wall measurement)

Purpose: establish that the flag changes crash to no-crash, and nothing else.
8-token generations, probe8 prompts
(`/home/mfeth/exp788/probe8.json`, `experiments/exp824-aa-estimator/FREEZE-824.md:20`).

| Arm | Flag | Call                                      | Preregistered expectation                                     |
| --- | ---- | ----------------------------------------- | ------------------------------------------------------------- |
| C0  | off  | batch 8, padded, CPU mask                 | rc≠0, message names two devices, site `modeling_olmoe.py:102` |
| C1  | on   | same                                      | rc=0, 8 rows × 8 new tokens                                   |
| C2  | on   | batch 1, all-ones mask                    | rc=0                                                          |
| C3  | on   | batch 1, left-padded to the batch-8 width | rc=0                                                          |
| C4  | off  | batch 1 bare ids                          | rc=0 (regression control)                                     |

Each arm is its own fresh process so a crash cannot contaminate the next.
Gate K1: all five match. Any miss → stop, report, no stage 2.
C0 reproducing exp810 on Winnie's tree also closes the gap that exp810 ran on a
different commit and card (`EXP-810.md:5`, `:25`).

### 5.4 Stage 2 — measured battery

**Config (inherit exp824 verbatim, `EXP-824.md:16-21`):** OLMoE-1B-7B-0125-Instruct,
offload `/home/mfeth/moe-offload-olmoe-0125-r05`, policy `lcnu`,
`device_memory_ratio 0.35`, `num_threads 4`, `gpu_only_expert_routing true`,
`adaptive_resident_mode legacy`, `speculative_prefetch` off, probe8, greedy,
`min_new_tokens = max_new_tokens = 128`. `CUDA_VISIBLE_DEVICES=1` mandatory (see R6).

**Arms.** A "block" always covers the same 8 prompts.

| Arm  | Loop   | Flag | Block content                                                                   | Role                                                |
| ---- | ------ | ---- | ------------------------------------------------------------------------------- | --------------------------------------------------- |
| N1   | native | off  | 8 sequential batch-1 bare-ids calls                                             | Today's shipped path; ties exp825 to exp820/821/824 |
| H1   | HF     | on   | 8 sequential batch-1 calls, each left-padded to the batch-8 width with its mask | Same loop and same padding as H8, batch 1           |
| H8   | HF     | on   | 1 batch-8 call, left-padded, mask passed                                        | Treatment                                           |
| WARM | —      | on   | 1 H8 block, 8 tokens, then 1 N1 block, 8 tokens                                 | Throwaway, never analysed                           |

Why H1 exists: H8 differs from N1 in loop (native vs HF), in padding, and in batch
size. H1 vs H8 isolates batch size. N1 vs H1 measures the loop-plus-padding change.
Without H1 a batch effect and a loop effect are indistinguishable.

Padding side: left, with `tokenizer.padding_side = "left"` set explicitly and
recorded. Right padding makes the last position a pad for short rows and is wrong
for causal generation.

**Battery** = one fresh process: WARM, then 6 pairs of (H1, H8) in ABAB order,
then 6 pairs of (N1, H1) in ABAB order. 24 measured blocks. Order of the two
pair-groups alternates across batteries. **n = 4 batteries.**
Rough wall, PROJECTION only: N1 and H1 blocks ≈ 8 × 128 × ~85 ms ≈ 90 s each using
the "~78–92 ms/tok (exp820/821 seals)" single-stream figure; H8 block unknown.
About 18 sequential-style blocks ≈ 27 min plus 6 H8 blocks per battery.

**Measurement standard (exp817 lineage, as frozen in `EXP-824.md:25-28`):** no
LD_PRELOAD, no sampler thread, no profiler, no `TorchDispatchMode`, no nvidia-smi
polling inside a battery. `perf_counter` around each `generate()` call. Host-state
row between batteries only.

**Statistic.** `stat(block) = Σ generate-call wall ms / Σ generated tokens`, with
the token count taken from recorded token lists, never assumed
(`EXP-824.md:32-33`). For H8 the denominator is the sum over the 8 rows.
This is whole-call wall, prefill inclusive, for every arm. Reason: the native path
drops `streamer` (P5), so a first-token timestamp is not obtainable the same way
in N1 and in H1/H8, and adding a hook would break the un-instrumented standard.
Prefill is therefore inside every arm's number; report it as such.

**Estimator.** Exactly exp824's: per battery, `d_i = stat(A_i) − stat(B_i)` for
i = 1..6; point estimate `mean(d)`; 95% percentile bootstrap, 10,000 resamples,
`numpy.random.default_rng`, seed fixed in the freeze manifest (`EXP-824.md:34-36`).
No min-of-3. Min-style difference reported as reference only.

**Launch gate.** Block-until-quiet: host load < 2.0 at launch and at battery
boundaries, budget 3600 s per wait (`EXP-824.md:22-23`, `FREEZE-824.md:23-24`).
Rationale: CI co-tenant load spikes of 7–35 on the 12-CPU host (from the brief).
`systemd-run --user`. GPU 0 untouched.

### 5.5 Gates (freeze before run)

Integrity:

- **G0 token integrity.** Every measured generation has a new-token count in
  {127, 128} (`EXP-824.md:45-49`). Every H8 call returns 8 rows. Compared lists of
  unequal length → battery INVALID, never truncated (`EXP-824.md:40-42`).
  Open point Q5: whether the HF loop and the native loop land on the same count.
- **G0b path integrity.** Each arm asserts which loop it used, from a cheap
  post-call fact: N1 asserts `native_engine.generate` was entered (call counter on
  the harness side, incremented outside the timed region); H1/H8 assert it was not.

Equivalence. Three layers, because free-running greedy agreement is chaotic after
the first divergence and its floor is battery-local: exp821's same-config floor
was 0.6553 (`experiments/exp821-capacity-policy-sweep/EXP-821.md:24`), and exp824
adopted 0.6503 from it (`EXP-824.md:48-49`); per the brief that floor did not
transfer, exp824 battery-1 measuring 0.5667 on the same config.

- **E1 teacher-forced logits (primary equivalence gate).** One extra fresh process,
  outside the wall battery. Forward the 8 prompts once as a padded batch and once
  each as batch 1 through `MoE.forward` (change C). For each prompt compare
  last-real-position logits. Gate: top-1 token identical for every prompt whose
  batch-1 top-1 margin (top-1 logit minus top-2 logit) is ≥ a threshold `m*`.
  `m*` is set from the same process's own noise: run the batch-1 forward twice and
  take `m*` = 4 × the largest observed |Δlogit| at the top-1 index across the 8
  prompts. Prompts under `m*` are reported, not gated. This tests "the mask and
  positions are right" without the chaos of 128 free-running steps. A padding or
  position bug shows up here as large logit differences on short rows and none on
  the longest row; report max |Δlogit| per prompt against prompt length for that reason.
- **E2 battery-local floor.** Within each battery, `floor_H1` = mean token
  agreement of H1 blocks 2..12 against H1 block 1 (12 H1 blocks per battery).
  Agreement = position-wise match rate over equal-length lists.
  No imported constant.
- **E3 batch-vs-single.** Mean agreement of each H8 block against the same
  battery's H1 block 1 ≥ `floor_H1` − 0.5 pp. Same margin convention as exp821 S1
  (`EXP-821.md:10`) and exp824 G1 (`EXP-824.md:48`).
  Also report, ungated: first-divergence index per prompt (H8 vs H1), and the same
  for H1 vs H1. If H8's median first-divergence index is not earlier than H1-vs-H1's,
  batching adds no divergence beyond the engine's own.
- **E4 loop equivalence, reported only.** N1 vs H1 agreement and first-divergence.
  Not gated: H1 is left-padded and N1 is not, so a difference here is expected and
  is not a defect of the fix.

Expected agreement, stated honestly: not bit-exact. Sources of legitimate
difference between H8 and H1 are masked attention over a wider padded batch,
multi-row GEMMs, and the dispatcher's multi-token branch with a different
accumulation pattern (2.4). E1 is the gate that distinguishes these from a real
plumbing bug.

Walls (struck if exp824 G2 fails):

- **W1 amortization, primary.** Per battery, 95% CI of `stat(H1) − stat(H8)`
  excludes 0 on the positive side in ≥ 3 of 4 batteries. Report the ratio
  `stat(H1)/stat(H8)` with both denominators, script-computed
  (`EXP-824.md:66-68`).
  The 7.2× figure is a PROJECTION for the orchestration share only; no gate is
  set at 7.2× or any fraction of it.
- **W2 loop cost, reported.** CI of `stat(N1) − stat(H1)`. Tells the operator
  whether moving to the HF loop costs or saves time at batch 1.
- **W3 headline, derived, reported only.** `stat(N1)/stat(H8)` across pair-groups
  is a cross-pair comparison inside one battery; label it as such and give no CI.

Validity and budget (as `EXP-824.md:57-65`):

- INVALID battery: any G0/G0b failure, non-zero exit, missing artifact, load > 2.0
  at a boundary. INVALID batteries are counted, not replaced.
- One attempt. Wall budget 6 h including quiet waits; on exhaustion stop and
  report aborted.
- Seal before analysis: tgz of raw per-block JSON, scripts, the patch diff, the
  freeze manifest; sha256 recorded; an independent verifier script re-derives the
  gates from raw artifacts (`EXP-821.md:13`).
- Prereg fallback, written now: if K1 fails or any H8 call raises in stage 2,
  adjudicate BATCHING-STILL-UNAVAILABLE, record the traceback verbatim, W1 = N/A.

### 5.6 What exp825 deliberately does not test

- Batch sizes other than 8. One contrast first.
- The op-count claim. exp810's P1 (ops/token batch-invariance, `EXP-810.md:5`)
  needs `TorchDispatchMode`, which is instrumentation. Run it as a separate,
  explicitly instrumented exp826 after exp825 seals; do not mix with wall arms.
- The serving path (`ContinuousBatchingEngine`). See R8.

---

## 6. Risks

**R1. Multi-token decode takes the dispatcher's prefill branch.**
`core/parallel/expert_dispatcher.cpp:1258-1260` forces a fetch regardless of cache
size when `batch_size > 1`, commented "only for prefill / only one extra cache slot
for prefill". With batch 8 this fires on every decode step. Eviction and residency
behaviour at `device_memory_ratio 0.35` may differ sharply from batch 1, and the
exp819–821 capacity findings do not transfer. Also `:1517-1520` and `:1659-1666`
add a masked gather and a `nonzero` scatter per active expert per layer per step.
Effect on W1: unknown, could erase part of the projected amortization.

**R2. Batch 8 activates more distinct experts per step.** Up to 8 × top-k routed
experts per layer per step instead of top-k, out of 16. On a CPU-offloaded store
that is more fetches per step. The projection amortizes orchestration, not expert
transfer. PROJECTION caveat, not a measurement.

**R3. Pad tokens are routed and cached.** Flattening happens in
`SyncOlmoeMoEBlock` (NOT IN CHECKOUT). Pad positions select experts during padded
prefill, which loads experts no real token asked for and feeds the tracer
(`big_modeling.py:1127-1132`) and precision observations
(`expert_executor.py:677-697`) with pad traffic. Real-row outputs are unaffected
in exact arithmetic; cache state and timing are affected. Mitigation in the
battery: H1 uses the same padding as H8 so the effect is in both arms.

**R4. KV-cache shape assumptions.**

- `self._cached_past_key_values` is one object per `MoE` (`big_modeling.py:833-835`,
  `:867-869`), reset at `:1351` and `:1375` on the native path only. On the HF path
  HF owns the cache, so there is no cross-talk, but the attribute is not cleared at
  `:1337-1340`. A native call after an HF call starts from `:1351`, which clears it. Safe.
- `seq_lens[0]` single-sequence assumption at `big_modeling.py:841-850` and
  `:977-986`. Not reached for OLMoE in `generate()` (2.3). It would be wrong for
  any batched paged path. Do not widen `_get_paged_attention_classes` as part of
  this work.
- Native logits are moved to CPU every step (`big_modeling.py:879`); the HF loop
  keeps them on the GPU. This is part of the loop difference W2 measures.

**R5. The `moe_store` attention shim is unreviewed.** `OlmoePagedAttention.forward`
falls through to `OlmoeAttention.forward` in `generate()` (exp771 stacks). Whether
it forwards the 4-D padding mask untouched on that fall-through cannot be checked
here. E1 is designed to catch a dropped mask: short rows would show large logit
error, the longest row none.

**R6. GPU 0 exposure.** The `lm_head` output hook moves logits to `device=0`
(`model_offload.py:2525-2531`) while the backbone is placed on the last visible
GPU (`:2979`, `:2993`; `big_modeling.py:773-774`, `:804`). With both GPUs visible,
every step would touch GPU 0, the shared CI runner. `CUDA_VISIBLE_DEVICES=1` must
be in the frozen launch line, and the harness must not hard-code `cuda:1`.

**R7. Recompute / graph paths.** CUDA-graph decode replay is serving-only and
refuses when transfer handlers or hooks are active
(`big_modeling.py:732-748`; `model_offload.py:993-1001`). Not reachable from
`generate()`. No interaction.

**R8. The serving scheduler is the engine's real batching path and is not what
this fix enables.** `MoE.generate()` is deprecated in favour of `serve()`
(`big_modeling.py:1199-1206`). `ContinuousBatchingEngine.add_request` / `step`
(`moe_infinity/serving/engine.py:571`, `:616`) builds on-device inputs correctly
(P12) and uses the paged OLMoE shim. It also refuses models without paged KV
unless `MOE_STRICT_PAGED_ATTENTION=0` (`serving/model_runner.py:60-72`). A result
from exp825 says nothing about serving throughput, and a serving experiment would
need its own harness.

**R9. Where the Winnie drift changes the patch.**

| Drift item                                                          | Effect on the fix                                                                                                           | Effect on the battery                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Base commit `0337988` instead of HEAD                               | None. `big_modeling.py` identical (empty `git diff --stat`). Line numbers in this report are valid on Winnie for that file. | Dispatcher line numbers differ: HEAD `:1258/:1518/:1659` ↔ `@0337988 :1292/:1558/:1699`.                                                                                                                                                                                                                                                                                                                                                    |
| `0337988` has grouped decode, fused router, FP8 path; HEAD does not | None on the Python diff.                                                                                                    | Batch 8 = 8 tokens per layer. Whether that is under the grouped kernel's token cap (`@0337988:...cpp:1841-1842`; constant value not located) decides if H8 would use it on eligible hardware.                                                                                                                                                                                                                                               |
| Grouped decode hardware gate                                        | None.                                                                                                                       | On a 4080-class card source says grouped decode is off (`@0337988:...cpp:1816-1818`, `hw_profile.py:42-49`). If runs set `MOE_GROUPED_DECODE=1` and believe it is active, check `grouped_batches` in dispatcher stats (`@0337988:...cpp:2761`). See Q4.                                                                                                                                                                                     |
| Modified `extensions/kernel/grouped_moe_prefill.cu`                 | None on the Python diff.                                                                                                    | **Material.** The kernel is exposed as `grouped_moe_prefill` (`core/python/py_archer_prefetch.cpp:214-219`; `@0337988: :263-268`). No caller exists in `moe_infinity/` at either commit, so the caller is in `moe_store` or there is none. If the caller selects by token count > 1, H8 decode steps run a locally modified kernel that N1 and H1 never touch. Record the diff's sha256 in the freeze manifest and state it in the writeup. |
| Untracked `runtime/rmsnorm_fusion.py`                               | None unless imported. Not present at HEAD.                                                                                  | Must be off in all arms, or on in all arms, and stated. It rewrites per-layer ops, so it changes the batch-1 baseline.                                                                                                                                                                                                                                                                                                                      |
| Untracked `model_offload.py.orig`                                   | Suggests `model_offload.py` was patched at some point. Git status on Winnie reportedly shows it unmodified now.             | Confirm `git diff --quiet HEAD -- moe_infinity/runtime/model_offload.py` on Winnie before freeze.                                                                                                                                                                                                                                                                                                                                           |
| `_store...so...bak`                                                 | None.                                                                                                                       | Confirms a native binary was swapped at least once. Record the sha256 of the loaded `.so` files in the manifest.                                                                                                                                                                                                                                                                                                                            |
| `moe_store` version                                                 | Unknown.                                                                                                                    | The shim and MoE block behaviour (R3, R5) come from it. Record `pip show moe_store` version and file hashes.                                                                                                                                                                                                                                                                                                                                |

**R10. Hardware label mismatch in the receipts.** exp809 and exp810 state
"RTX 6000 Ada" (`experiments/exp809-op-stream-census/EXP-809.md:5`, `EXP-810.md:5`);
exp824's freeze states "RTX 4080 16 GB class, 16,311 MiB" (`FREEZE-824.md:16`).
If these are different cards, exp810's crash was never observed on the exp825 rig,
which is another reason stage 1 arm C0 is not optional.

---

## 7. Open questions for the operator

- **Q1 (blocks launch).** In the exp810 seal, what frame sits directly above HF in
  the B1 traceback, `big_modeling.py:1340` or `:854`? And what was
  `use_native_engine` in that harness? Section 3 H4 and stage 0 depend on it.
- **Q2.** In exp810 attempt-3, which device was `attention_mask` on when
  `position_ids` was moved to CUDA? If the mask was on CUDA too, H1 and H2 are
  both wrong and the fix as designed would not help.
- **Q3.** Can someone with the `moe_store` source confirm what
  `OlmoePagedAttention.forward` does with `attention_mask` when no paged context
  is set (`olmoe_paged_attention.py:108` region), and whether `SyncOlmoeMoEBlock`
  calls `grouped_moe_prefill` for token counts > 1?
- **Q4.** Is grouped decode really active on Winnie today? Source says the card
  fails the RTX PRO 6000 gate unless `MOE_INFINITY_UNVALIDATED_HW=1` is set. If it
  is not active, the `grouped-decode-determinism-is-expert-order` note describes
  the per-expert `index_add_` path, not the grouped kernel.
- **Q5.** Should H1 force the HF loop through the patch's guard (padded batch-1
  input, as designed) or through `use_native_engine=False`? The second needs no
  padding at batch 1 but changes memory-coordinator setup
  (`big_modeling.py:419-429`, `:521-531`) and so changes more than the loop.
- **Q6.** Is 0.35 the right `device_memory_ratio` for a batch-8 arm, given R1 and
  R2? Keeping exp824's value preserves comparability; it may also be the setting
  where batch 8 thrashes most. One value must be frozen; I would keep 0.35 for the
  first battery and treat capacity as the follow-up.
- **Q7.** Which tree should carry the patch: Winnie's local `0337988` checkout as
  recorded drift, or a branch off Mack HEAD that Winnie then installs? The diff is
  identical; the second changes the engine under every other frozen baseline.
- **Q8.** exp810 and exp809 name an RTX 6000 Ada; exp824 names a 4080-class card.
  Same host with a relabelled card, or two machines?
