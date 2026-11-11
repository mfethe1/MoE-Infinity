# PREREG-767 — Native-vs-python split of the speculative-prefetch cost

Written BEFORE any exp767 run. Working dir `~/warp-work/exp765-prefetch-cost-repair/`.

## Claim under test
exp764 attributed +7.53 s/cell of SPEC-arm cost to
`ExpertPrefetcher.speculative_prefetch` leaf self-time (lines 446-450 cluster =
torch.topk / numpy conversion region). Those stacks were collected WITHOUT
`--native` and contain ZERO libtorch frames (verified: `grep -c libtorch
PROF_SPEC.pyspy` = 0), so native callee time (torch ops + device sync) was
charged to the Python frame. Hypothesis: the majority of that time is NATIVE
(torch kernel dispatch / D2H transfer / sync), not Python bytecode.

## Method
Envelope = exp764 verbatim (OLMoE-1B-7B-0125-Instruct, src753 @ b7f6ca4,
lcnu r=0.75, threads 4, gpu-route off, GPU1, 6 prompts x 64 tok, warmup 1,
2 cells/arm: NAT_LGC = `off off off`, NAT_SPEC = `on off off`).
Single change: `py-spy record --native -r 100 -f raw` (probe verified on
Winnie: spawn mode, 0 errors, libtorch_cpu.so symbols present, 100.5 Hz).
Observation-only: no wall-clock claims vs unprofiled runs.

## Classifier (literals probed on sealed exp764 artifacts 2026-11-11)
- inside-sample: any frame matches
  `speculative_prefetch \(moe_infinity/(distributed/expert_executor|memory/expert_prefetcher)\.py:`
  (executor wrapper observed at expert_executor.py:209/210; prefetcher body at
  expert_prefetcher.py:446/447/450/468).
- leaf families: PY_PREF (leaf `.py:` in memory/expert_prefetcher.py),
  PY_EXEC (leaf in distributed/expert_executor.py), PY_OTH (other `.py:`),
  N_TORCH (leaf contains libtorch_cpu/python/cuda.so, libc10.so, libgomp),
  N_LIBC (libc.so/libpthread/librt/libcuda.so/cuda*Sync/cudaMemcpy/__intercept),
  N_HEX (leaf starts 0x), N_OTH.
- Native-frame formats verified against the 2026-11-11 native probe
  (/tmp/native_spawn.raw: `symbol (libtorch_cpu.so)`, `0x... (libc.so.6)`).

## Decision rule (frozen)
P = secs(inside_SPEC) - secs(inside_LGC) at 100 Hz.
NATIVE = sum of positive family deltas over {N_TORCH,N_LIBC,N_HEX};
PYTHON = sum over {PY_PREF,PY_EXEC,PY_OTH}; shares normalized over NATIVE+PYTHON.
- rc=1 D1 NATIVE-DOMINATED: native_share >= 0.70 -> successor exp768
  transfer-restructure repair (device-side topk, async D2H of K indices,
  single sync point; prefetch decisions identical).
- rc=2 D2 PYTHON-DOMINATED: python_share >= 0.70 -> successor exp768 applies
  the staged t3 micro-patch (patched/expert_prefetcher.py,
  sha256 55b34db95278935f..., REPAIR-DESIGN a6648057bc3bc46e).
- rc=4 D3 MIXED: both shares in (0.30, 0.70) -> exp766 combines repairs
  ranked by share.
- rc=5 D5 NULL-TIME: P < tau = 2.0 s -> premise wrong, redesign.
- rc=3 INCONCLUSIVE: combined samples < 30,000 -> remedy = repeat identical
  protocol with appended stacks (exp764b precedent), NEVER lower the gate.
- rc=9 IDENTIFY-FAIL: SRC_HEAD != b7f6ca4.
tau=2.0 s > sampling noise (leaf counts ~sqrt(N); at ~750 expected samples the
1-sigma leaf noise is ~0.1 s) and > 2% of ~105 s cell wall.

## Known benign artifacts (pre-registered)
- Banner `exp752 mode=2`: env alias RC resolves to int 2 (exp764 SETTLEMENT,
  family precedent). Runner greps the resolved int. Any BANNER-FAIL line is a
  template defect, not a cell failure; adjudicate via cell-log grep.
- BADIO requires empty .pyspy with RC recorded.

## BELIEFS update rule
Whichever branch lands, engine_overhead posterior gains one descriptive
observation: s=0.5 w=0.5 (attribution-only, no engine change measured).
If D1: io_overlap unchanged; new candidate direction `index-transfer-restructure`
opens with prior from this P. If D2: engine_overhead gets s=1 w=0.5 (Python
bookkeeping confirmed as the mechanism).

## Fixtures (must pass pre-freeze)
synthetic raw stacks exercising: D1 native-rich, D2 python-rich, D3 mixed,
sample-gate fail, SRC_HEAD fail, DATA-FAIL missing file.

## Chain of custody
Runner derived verbatim from run_exp764.sh (additive: --native, NAT_ ids,
resolved-int banner, exp765 in busy-gate). engine_arm765.py = byte-identical
copy of engine_arm764.py (sha 9e874ab2e5a7b66e...). FREEZE-765 written on
Winnie pre-run with all shas.

## ADDENDUM R1 — renumber exp765 -> exp767 (pre-run, 2026-11-11T03:4xZ)
Filesystem name collision discovered at launch: /home/mfeth/exp765 on Winnie
belonged to the peer rc-contention-determinism lane (created 23:17:04Z, SEALED:
REPLAY-765.txt CONTENTION-SAFE, all cells OK, review APPROVE-WITH-NITS).
No exp765(warp) cell ever ran (no NAT_ files, no runner.log, no processes);
my staging was additive only (7 files + out/FREEZE-TIME.txt, nothing of theirs
overwritten; their out/ENV.txt would have been clobbered HAD the runner started
— it did not). My artifacts relocated to /home/mfeth/exp767; my files removed
from their sealed dir. Runner path-only diff exp765->exp767 (sha 82cf8a85 ->
new, recorded in FREEZE-767); analyzer logic byte-identical modulo
renumber strings; fixture battery re-run post-rename. Number 766 deliberately
left to the peer lane.
