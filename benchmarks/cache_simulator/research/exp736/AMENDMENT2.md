# exp736 AMENDMENT2 — probe WSL interop sockets per powercfg call (supersedes AMENDMENT1's fixed socket)

Second start (2026-11-06T13:49:42Z) still failed: /run/WSL/1_interop and 2_interop are stale ("Invalid argument");
the sockets of live /init processes (1160, 68921, and session sockets) work. Unit stopped again before any cell
output (out/ held only RUN_SHA256); moved aside to out.abort-A1, not used.
Change: run_exp736.sh's powercfg calls go through pc(), which tries each /run/WSL/*_interop socket (oldest first) and
uses the first that succeeds; it is re-probed on every call, so a socket dying mid-run cannot silently drop the plan
switch. A failed call leaves the plan unapplied, and the existing "plan not applied" flag catches it. Everything else is unchanged.
