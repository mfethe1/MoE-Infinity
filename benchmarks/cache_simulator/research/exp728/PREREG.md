# exp728 PREREG — multi-GPU prefetch-hit device bug in MoE-Infinity: reproduce, fix, verify, then answer exp725's question

Frozen BEFORE any exp728 run, and before the patch has been compiled or executed anywhere. Lane 79990, STACK-1001.
Namespace exp728 checked free (exp724-727 exist; exp727 belongs to a concurrent unit of this lane).

## Finding being tested (from exp725, in flight)
With `CUDA_VISIBLE_DEVICES=0,1` every exp725 two-GPU cell so far (3/3) failed at the first decode with
`RuntimeError: Expected all tensors to be on the same device ... cuda:0 and cuda:1!`, re-raised from the native
`expert_dispatcher.wait_expert()`. Single-GPU cells pass. Source diagnosis (upstream main 0337988,
`core/parallel/expert_dispatcher.cpp`): `Enqueue`'s cache-hit path routes execution to the expert's resident GPU
(`args.gpu_id = node->device.index()`), but `GPUFetchFunc`'s wait-for-prefetch path (expert became resident while a
prefetch was in flight) pushes to `exec_queue_[gpu_id]` of the *fetch worker*. Under round-robin multi-GPU placement
the prefetch can land the expert on the other GPU, so the exec worker moves inputs to `gpu_id` while weights are on the
resident device. Patch (`fix.patch`, +7/-2): use `resident_gpu = node->device.index()` for the exec queue and for the
`ActiveGeneration` lookup in that branch only. Single-GPU behaviour is provably unchanged (resident == gpu_id).

## Design (Winnie, after exp724-727 finish; serial GPU use)
Build: detached worktree of the installed tree's repo at 0337988 + fix.patch, `setup.py build_ext --inplace` with the
same flags as the installed build (SM120). Arm P runs via `fixrun.py` (drops the editable-install finder, asserts that
`moe_infinity` and `_store` load from the fix tree, writes provenance per cell). Arm U = the installed, unpatched
engine; its tree status is recorded (`unpatched_tree.txt`).
Cells (lcnu, OLMoE-1B-7B, 6 prompts, greedy 64 tokens, warmup 1; engine_arm.py == exp724/725 sha ec360baf21029ac1):
U g1 r0.2 | U g0,1 r0.2 | P g1 r0.2 | P g1 r0.4 | P g0,1 r0.2 | P g0,1 r0.1 — 3 blocks, shuffled Random(728+block).
Contamination rule (pre-registered, exp724 lesson): a cell is flagged if, before it starts, any GPU it uses shows
>1024 MiB, or the Windows Ollama API reports a loaded model at the start or at any 5 s sample during the cell. Flagged
cells count for correctness gates but are excluded from every speed comparison.

## Gates (analyze.py frozen)
- REPRO: unpatched two-GPU cells fail with the device-mismatch message in >=2/3 blocks -> REPRODUCED.
- FIX: all 6 patched two-GPU cells complete, provenance confirms the fix tree, and in every cell >= 5/6 prompts give
  output token ids identical to the unpatched single-GPU reference -> FIXED (exp724 G0 found 33/33 cells identical
  across GPUs, ratios and policies, so exact parity is expected; one near-tie flip from cross-device accumulation order
  is tolerated). All ran, but parity fails -> RUNS-BUT-DIVERGES. Else PARTIAL / NOT-FIXED.
- NOREGRESS: patched vs unpatched single-GPU r0.2 outputs identical in all 3 blocks and median clean-pair tok/s ratio
  in [0.95, 1.05] -> NOREGRESS. Outputs identical but no clean pair -> NOREGRESS-OUTPUTS-ONLY. Else REGRESSION?
- MIXED (secondary; the exp725 question at equal total cache budget): mean clean tok/s of P g0,1 r0.2 over P g1 r0.4
  (each needs >=2 clean cells): >=1.05 MIXED-WINS, <=0.95 MIXED-LOSES, else MIXED-TIE; otherwise MIXED-UNDETERMINED.
  Prediction (stated now): MIXED-LOSES, because exp724 measured GPU0's gen3 x2 link at 3.6-5.1x slower decode, and
  round-robin puts half the experts behind it.
- Verdict: `VERDICT <REPRO>|<FIX>|<NR>|<MIX> [COMPLETE|INCOMPLETE(n missing)]` (expected-to-fail U two-GPU cells are
  not counted as missing).

## Consequence pre-committed
REPRODUCED+FIXED+NOREGRESS -> open an upstream PR with the patch and this evidence (posting approved by Michael for
experiment results / upstream PRs). If MIXED-LOSES as well, the follow-up is link-weighted placement (experts per GPU
proportional to measured link bandwidth) as its own preregistered experiment. Any other outcome -> no PR; diagnose.

## Bayesian update (BELIEFS.json)
`placement` ("link-aware placement beats shipped round-robin on mixed-link hosts"): MIXED-LOSES s=1, TIE 0.5,
WINS s=0; weight 1.0 (n=3 blocks, real engine), halved if fewer than 3 clean cells per arm.
New `engine_correctness_multigpu` is reported as a fact (fixed or not), not as a belief.
