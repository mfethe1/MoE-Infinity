# exp728 AMENDMENT 2 — pre-run (no exp728 build or cell has executed; unit still waiting on exp725-727)

Observation (2026-11-06 04:32 UTC): an unrelated workload, `~/wsp/sm-exp058-run/gen.py` (CUDA_VISIBLE_DEVICES=1,
~4.4 GB RSS, ran ~28 min at the time of observation, owner lane not registered on Mack), shares Winnie GPU1 with this lane. exp725's
single-GPU OLMoE cells measured 2.8-4.0 tok/s versus 9-11 tok/s in exp724's clean GPU1 cells; GPU1 showed ~15.2 GB
used while an exp725 r0.4 cell ran. No GPU lease convention exists on Winnie.

Change (runner only; cells, arms, gates, thresholds and the contamination rule are unchanged):
- before each cell, `quietwait.sh <gpus> 2700` waits up to 45 min (30 s polls) for every GPU the cell uses to show
  <=1024 MiB and for Ollama to report no loaded model; it then runs the cell regardless. Waited seconds and
  QUIET|TIMEOUT are logged to out/quietwait.csv.
- The pre-registered contamination rule still decides exclusion; this only reduces how many cells it has to exclude.
- Not used for exclusion and not used by analyze.py.
