# exp759: head-to-head of our PR #353 vs upstream PR #354 in one sealed envelope

Pre-registered 2026-11-10T17:0xZ, **before any exp759 timing data exists** (smoke runs are functional-only, excluded
from evidence). Tier: native-GPU end-to-end engine decode (Winnie WSL2, RTX 5060 Ti 16 GB, GPU1).

## Why now (live engagement question)

Two open PRs claim the same retire-by-event decode win on `core/parallel/expert_dispatcher.{cpp,h}`:

- **PR #353 (ours)**: head `b7f6ca4` — event-poll retirement + completion queue behind `MOEI_EXP752_MODE` (H|R|RC),
  +99/−2 surgical. exp752 measured RC−H = −8.20 ms/tok (sealed, WSL).
- **PR #354 (upstream maintainer `drunkcoding`)**: head `827019db` — unified event polling, unconditional, +278/−204.
  exp756 measured P34 vs fresh H = +11.962 ms/tok in this same envelope family (SEALBAR P34 vs sealed RC = −1.949).

exp752 (RC vs H) and exp756 (P34 vs H) ran on **different days/thermal states**; the P34-vs-RC comparison so far is
only a cross-run SEALBAR. Upstream will merge at most one of the two implementations. This experiment measures both
candidates **and** the shared control in one interleaved envelope on one GPU in one session.

**Primary question:** P34 vs RC head-to-head in matched conditions — faster, slower, or equivalent within THR?

**Secondary questions:** (a) does each candidate replicate its win vs fresh H in-envelope (bar 0.5× the sealed −8.20);
(b) do outputs stay byte-identical to the sealed clean references (fail-closed parity)?

## Arms and builds

| arm | code state | build path | env | banner |
|-----|-----------|------------|-----|--------|
| H   | sealed exp752 build (drift control + shared anchor) | `/home/mfeth/exp752/src` | `MOEI_EXP752_MODE=H` | `exp752 mode=0` |
| RC  | **our PR #353 head `b7f6ca4`** (fresh private build) | `/home/mfeth/exp759/src753` | `MOEI_EXP752_MODE=RC` | `exp752 mode=2` |
| P34 | **upstream PR #354 head `827019db`** (proven exp756 build, unmodified) | `/home/mfeth/exp756/src` | mode unset | banner absent |
| hf  | transformers bf16 reference (drift anchor, informational) | — | — | — |

Composite (RC+P34) arm is **out of scope**: both PRs restructure the same dispatcher region (+278/−204 vs +99/−2);
composing them is a semantic merge, not a build — excluded to keep this experiment a clean matched comparison.

## Sealed references (exp752, quiet-only clean cells, frozen)

| arm | ms/tok (median of clean) | clean cells | refs frozen for parity |
|-----|--------------------------|-------------|------------------------|
| H   | 93.903 | H_2 96.483, H_3 91.323 (H_1 FOREIGN-excluded) | `refs/H_2.json`, `refs/H_3.json` |
| RC  | 85.699 | RC_2 85.210, RC_3 86.188 (RC_1 excluded) | `refs/RC_2.json`, `refs/RC_3.json` |
| hf  | 31.791 | 3 clean | — |

exp756 P34: 83.750 (n=3), parity byte-identical to `refs/RC_2/RC_3`.

## Design

10 serial cells on **Winnie WSL2 GPU1** (`CUDA_VISIBLE_DEVICES=1`), interleaved order (spreads drift):
`hf_1, H_1, P34_1, RC_1, H_2, P34_2, RC_2, H_3, P34_3, RC_3`.

Envelope identical to exp752/exp756 (byte-same `prompts.json` `6d06ff56…`, `engine_arm.py`, `hf_arm.py`, monitors,
`allquiet746.sh`): OLMoE-1B-7B-0125-Instruct, offload store `~/moe-offload`, policy lcnu, ratio 0.75, `--threads 4`,
`--gpu-route on`, 6 prompts × 64 new tokens greedy, warmup 1, timeout 1800 s per cell.

Exclusion gates (fail-closed, per-cell, exp746 AMENDMENT1 / exp751 / exp752 / exp756 family):
quiet-wait gate before every cell; pre-start GPU1 memory ≤ 1024 MiB; no Ollama-loaded models; no CI runner workers;
loadavg mean ≤ Q_LOAD_MAX 4.0; foreign GPU compute procs = 0; NVML util baseline ≤ 5%; ≥10 util samples per row;
banner-mode gate per arm (H=0, RC=2, P34 absent) + `gpu_route_effective`; out_ids present for all 6 rows.
A successful rerun clears that cell's stale FAILED entry; failed cells excluded, never silently re-run otherwise.

## Frozen bars (THR = 3.0 ms/tok, exp752 continuity; comparisons rounded to 3 dp before bars)

- **PRIMARY (head-to-head):** d = median(P34 clean) − median(RC clean).
  |d| ≤ 3.0 → **HEAD-TO-HEAD-EQUIVALENT**; d > 3.0 → **P34-FASTER**; d < −3.0 → **RC-FASTER**.
- **SECONDARY replication:** RC−H ≤ −4.10 → **RC-REPLICATED-IN-ENVELOPE** (0.5× sealed −8.20);
  P34−H ≤ −4.10 → **P34-REPLICATED-IN-ENVELOPE**.
- **PARITY (fail-closed, gates everything):** every clean engine cell's out_ids must equal BOTH sealed refs for its
  arm AND the fresh cells of the other engine arms (all three arms must decode byte-identically). Any divergence →
  **PARITY-FAIL**, no admitted timing claims this run (descriptive timings only, labelled as such).
- **Consistency:** |fresh H − 93.903| ≤ 4.0 **gates the envelope** (violation → verdict suffix `ENV-DRIFT`, all timing
  labels become descriptive); |RC − 85.699| ≤ 3.0 and |P34 − 85.699| ≤ 3.0 are **reported only** (the head-to-head
  delta is robust to shared drift by design; a seal miss on one arm alone is a finding, not an automatic fail);
  |hf − 31.791| ≤ 3.0 informational at n=1.
- **INCONCLUSIVE(n)** if any engine arm has clean n < 2.

Verdict precedence: PARITY-FAIL > INCONCLUSIVE(n) > bars.

## Amendments

None. Amendments are allowed only before any exp759 timing data exists, and must be recorded in `FREEZE-759.txt`
with sha256 of every amended file plus the reason.
