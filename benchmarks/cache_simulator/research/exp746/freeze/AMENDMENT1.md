# exp746 AMENDMENT1: one combined quiet wait; contaminated cell q_hf_1 aborted and rerun

Written 2026-11-06 ~22:05 EST (03:05Z), during cell q_hf_1. The frozen analyzer, cells, arms, prompts and decision rules are
unchanged. This amendment only changes how the runner waits before each cell starts.

## What happened (raw evidence on Winnie ~/exp746/out, preserved under out/aborted-A1/)
- The frozen runner waited for a quiet GPU first (`quietwait.sh`) and for a quiet CPU second (`loadwait.sh`). q_hf_1 passed the GPU
  wait at t=0 and then waited 3397 s for CPU load. In that window a foreign process (`~/wsp/venv/bin/python gen.py`, `timeout 1950`,
  another lane) started on GPU1. precell.csv: gpu1=10260 MiB at start. mon.sh recorded the foreign PIDs mid-cell, and HF ran at
  ~3.7 tok/s (quiet HF in exp743: ~30 tok/s).
- The frozen rule already FLAGs this cell, so it could never have entered a speed comparison. Letting it finish would just waste a
  quiet-HF replicate.

## Change
- `allquiet746.sh` (new) is ONE bounded wait (≤5400 s, 20 s poll). It holds until all of these are true at the same moment: GPU ≤1024
  MiB, no Ollama model, loadavg1 <3.0, no Runner.Worker. These are the same thresholds as the two frozen waits combined.
- `run_exp746.sh`: `QW=$(allquiet746.sh ...)` and `LW="$QW"`, so the precell.csv format is unchanged. `allquiet746.sh` is added to
  RUN_SHA256. Diff vs freeze: 2 lines.
- The aborted q_hf_1 artifacts (q_hf_1.*, FLAGGED, FLAGGED.why, precell.csv, RUN_SHA256) were moved, not deleted, to
  `out/aborted-A1/`. No other cell had started. q_hf_1 then reruns under the combined wait. The settle job must report the aborted
  attempt.
- Freeze for amended files: `AMENDMENT1.sha256`. The pre-start flag rule, mid-cell foreign-PID flag and all exclusions still apply.
