# FREEZE-824 — exp824 A/A estimator validation

Frozen 2026-11-18T12:41Z UTC, BEFORE launch. Prereg
gates, estimator spec, tolerances and rules do not change after this point.

| file | sha256 |
|---|---|
| EXP-824.md (prereg) | 5511ffb0cf2b4ef8120ad97d7ca74846ca139c971955b0fc37264a9c1088a182 |
| p14_batt.sh (battery script) | 6761e4df856959c755a3f60041df4451c6adf73b15432427a05a3c318a3281cf |
| run824.sh (orchestrator + extractor) | 513e04efef718e9acc09278008b11fe631d68838ed885ec3a44dc3eacc83d481 |
| parent p11_run.sh (exp821, reference) | 69e1fc8a84130786a16c6d46bbaf26f9049efce49615ec93473dd1b90bda1777 |
| parent run821.sh (exp821, reference) | 4d034ab158efdc45c2e43f5e990dac3e7ae79d519e369947a06a4e93889f0374 |

Environment: Winnie WSL Ubuntu, GPU 1 (RTX 4080 16 GB class, 16,311 MiB), GPU 0
untouched (shared CI runner). Engine: editable install of ~/moei-engine/MoE-Infinity
@ git 033798811664f5d89cae58049ff16e912ebc5862; venv ~/venvs/moei-engine (python 3.12). Model
/home/mfeth/models/OLMoE-1B-7B-0125-Instruct; offload /home/mfeth/moe-offload-olmoe-0125-r05;
prompts /home/mfeth/exp788/probe8.json (exp821 battery parent, unchanged).

No engine source patch, no binary swap, no LD_PRELOAD (un-instrumented truth standard).
Bootstrap seed 20261118, 10,000 resamples. Launch: systemd-run --user, unit exp824-battery,
quiet-gated (<2.0 load at launch checks per wait_quiet), one attempt, 5h wall budget.
