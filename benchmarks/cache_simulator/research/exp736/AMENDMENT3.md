# exp736 AMENDMENT3 — loop stdin bug: resume after cell 1

Third start (2026-11-06T13:53:13Z) ran cell m_g1_A, then exited the cell loop (EXP736-DONE at 14:05:17Z, power plan
restored to Balanced by the trap). Cause: the cell list was piped into `while read`, and powercfg.exe (WSL interop)
reads stdin and consumed the remaining lines. No other cell started.
Change: the loop reads the cell list on fd 3 (`while read -u 3 ...; done 3< <(...)`). The previous RUN_SHA256 is kept as
RUN_SHA256.prev-*; the new one also covers AMENDMENT3.md. The run RESUMES in the same out/: m_g1_A (already complete under
the frozen micro.py; FLAGGED "mid-cell ollama model loaded" by mon.sh) is kept and skipped by the existing
skip-if-present rule. It is descriptive only and has no decision rule. Cells, arms, rules and analyze.py are unchanged.
