# exp726 AMENDMENT 1 — pre-run (no exp726 cell has executed; unit still waiting on exp725)

Why: exp724 lost 4 cells to an Ollama co-tenant on GPU1, and on 2026-11-06 an unrelated workload
(`~/wsp/sm-exp058-run/gen.py`, CUDA_VISIBLE_DEVICES=1) was observed sharing GPU1 while exp725's single-GPU cells ran at
2.8-4.0 tok/s versus 9-11 tok/s clean. exp726's gates (FLOOR, OVERHEAD) are pure speed ratios, and its prereg
predates the contamination lesson.

Change (runner only; cells, arms, analyze.py and gate thresholds unchanged):
- before each cell, `quietwait.sh 1 2700` waits up to 45 min for GPU1 <=1024 MiB used and no Ollama model loaded,
  then runs the cell regardless.
- pre-start GPU1 MiB and Ollama model count (-1 = probe failed) are logged to out/precell.csv; a cell is FLAGGED if
  GPU1 >1024 MiB or the count != 0. The flagged list is appended to verdict.txt.
- Consequence fixed now: the sealed verdict is reported as analyze.py prints it. If any cell is FLAGGED, the verdict
  is labelled CONTAMINATED for the record and its Bayesian weight is halved (engine_overhead direction); flagged
  cells are not silently dropped.
