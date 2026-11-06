# exp728 AMENDMENT 1 — pre-run, before any cell or build executed

Written 2026-11-05 ~23:35 EST while the exp728 unit was still waiting on exp725-727 (no out/ directory existed).

Defect: run_exp728.sh probed the Windows Ollama API at the WSL default-gateway IP. A live check from WSL showed
`gateway:11434 -> HTTP 000` (unreachable) and `127.0.0.1:11434 -> HTTP 200`. Because `curl ... | grep -c` prints 0
on a failed request, every cell would have been recorded as "no Ollama model loaded", silently disabling the
pre-registered contamination rule.

Change (runner + analyzer only; gates, cells, arms, thresholds unchanged):
- probe `http://127.0.0.1:11434/api/ps`; count loaded models with `grep -o '"name"' | wc -l`; a failed probe records -1.
- analyze.py flags a cell when the pre-start Ollama count is != 0 (was > 0), so -1 (unknown) is treated as
  contaminated — fail-closed. The during-cell monitor rule already flagged any value other than 0.
