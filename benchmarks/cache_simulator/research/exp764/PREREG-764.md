# PREREG-764 — SPEC-policy CPU attribution (py-spy sampling)

Written 2026-11-10T23:1xZ, before any profiling run. Follows exp763 D4 verdict
(+7.8 s/cell unattributed policy CPU, zero excess traffic). Descriptive, w=0.5.

## Question
Which code regions account for the SPEC-vs-LGC unattributed CPU delta measured by
exp763? (Target: the #1 candidate exec-path-handoff needs a precise motive.)

## Method (observation-only; NO engine code change)
- Run engine spawn-mode under py-spy: `py-spy record -r 100 -f raw -o <cell>.pyspy`
  wrapping the same runner command as exp762 cells, one LGC cell and one SPEC cell
  (identical prompts, seed, model dir; io traces on as usual for run identity).
- py-spy installed via pip into the lane venv (version recorded in FREEZE-764).
- Profiling overhead acknowledged: NO wall comparisons against exp762 baselines and
  no throughput claims; only intra-profiled relative stack attribution is evidence.

## Aggregation (frozen before profiles exist)
Self-time share by stack family, families fixed now:
  F1 speculation-policy loop (draft/spec-head selection, prefetch decision code)
  F2 verification (accept/reject scan of draft tokens)
  F3 batch reshape/scheduling (tensor assembly, index rebuilds, queue ops)
  F4 kernel-dispatch glue (aten/cuda launch paths outside traced stages)
  F5 other (incl. sampler, tokenizer, misc)
Analyzer maps each raw record leaf frame to a family by module/function substring
rules fixed in analyze764.py BEFORE running (literal engine module names verified
against the engine source tree at freeze time).

## Decision rule (fixed)
Compute delta_share = self_time_SPEC − self_time_LGC per family (seconds, from
sampling counts × 1/100 Hz).
- A5 SINGLE-DOMINANT: one family ≥ 50% of total positive delta → that family is the
  cost; follow-up targets it directly.
- A2 SPLIT: top two families ≥ 70% combined (and not A5) → cost split, follow-up
  ordered by share.
- A0 DIFFUSE: neither → cost spread; follow-up = restructure exec path wholesale
  (strengthens exec-path-handoff; deprioritize micro-fixes).
Also report: absolute LGC profile top-5 (context), and per-family SPEC/LGC seconds.

## Gates
- Engine identity: same model dir fingerprint + same runner sha as exp762 cells
  (rc0 runs only; any crash → attempt void, no re-run without prereg note).
- No timing/performance claims anywhere (descriptive class).
- Leak scan before any external post; POST-once + readback + ledger receipt.
- Exit codes: 0 ATTRIBUTED-<A5|A2>, 3 INCONCLUSIVE (samples < 30k total or
  families unmappable > 20%), 4 DATA-FAIL, 9 IDENTIFY-FAIL (model fingerprint
  mismatch).

## Freeze
FREEZE-764.txt: sha256 of this prereg + analyze764.py + py-spy version + engine
runner sha, written on Winnie BEFORE profiles are taken.
