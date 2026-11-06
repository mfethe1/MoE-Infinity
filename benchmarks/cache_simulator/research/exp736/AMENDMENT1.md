# exp736 AMENDMENT1 — WSL interop for powercfg.exe inside the systemd unit (before any admitted cell)

Start at 2026-11-06T13:48:10Z: `powercfg.exe: Invalid argument` for every call, because the systemd user unit lacks
WSL_INTEROP. The unit was stopped before any cell output (out/ held only RUN_SHA256; precell.csv empty). That out/ was
moved aside to out.abort-A0 and is not used.
Change: run_exp736.sh exports WSL_INTEROP=/run/WSL/1_interop (init's interop socket; falls back to the newest
/run/WSL/*_interop) before the first powercfg call. Verified in a transient unit: `powercfg /getactivescheme` -> Balanced.
RUN_SHA256 also covers AMENDMENT1.md. Cells, arms, decision rules and analyze.py are unchanged.
