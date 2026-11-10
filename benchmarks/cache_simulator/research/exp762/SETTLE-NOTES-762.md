# exp762 SETTLE NOTES (written 2026-11-10T20:35Z — BEFORE any cell ran; outcome-blind)

## Launch-condition state (attempt-2, unit exp762run started 2026-11-10T20:31:19Z)
- PREREG line: "Launch ONLY after exp761 settles; busy-gate includes exp761 units."
- At gate time all exp units incl. exp761run were inactive (exp761run done 20:06:44Z, verdict written).
- UNKNOWN to the gate: tier1 lane (warp-lane-7687a6bf1295) relaunched run_exp761.sh
  DETACHED at 20:17:45Z (CG3 rerun, bash pid 3834035, engine pid 3845198) — outside
  systemd, not reflected in running.json at launch. GPU1 busy (16GB, 55-87% util).
- Consequence: busy-gate passed; runner is protected by the PER-CELL allquiet746 gate
  (≤1024MiB + ollama idle + loadavg<3 + no Runner.Worker, up to 5400s per cell).
  At 20:33Z: zero precell rows, runner parked in allquiet for cell 1. No contamination.

## Pre-registered settle rules (bind settle adjudication; analyzer untouched)
1. Cells listed in out/FLAGGED (pre-start GPU>1024MiB or ollama loaded) or whose
   precell.csv row shows TIMEOUT (non-quiet entry into cell) are INVALID for verdict
   purposes regardless of analyzer exit code (family precedent: exp759/exp760 settle
   FLAGGED exclusion).
2. The frozen analyzer's printed verdict + exit code stand as RECORDED evidence.
   If the flagged set intersects the analyzer's valid cells, settle records
   CONTAMINATED and executes DECISION-TREE B5 (INCONCLUSIVE → rerun-once) instead
   of B1/B2 admission. If flagged set is empty, settle proceeds per DECISION-TREE
   directly on the analyzer verdict.
3. Attempt-1 (20:27:52Z) exit-9 identity-grep false-negative is VOID (see
   VOID-ATTEMPT-1.txt): zero cells, no data. Freeze attempt-2 is the operative
   freeze (run_exp762.sh c705e171…, PREREG ec919d29…, FREEZE b181dcaf…).

## Banner-format clarification (written 2026-11-10T20:52Z, mid-run, before any timing data examined)
Runner banner gate greps "exp752 mode=RC" — WRONG STRING, always was. The engine banner
format is `exp752 mode=%d` (numeric, from _store strings). Proof mode=2 == RC:
exp760 (sealed a30f005, same build /home/mfeth/exp759/src753, MOEI_EXP752_MODE=RC)
printed `exp752 mode=2` in 24/24 cell logs; exp759's mode-0 cells printed mode=0
(their A/B was mode 0 vs RC). exp761 (H build) printed mode=0 likewise.
SETTLE RULE: out/BANNER-FAIL entries for cells whose log contains `exp752 mode=2`
are FALSE ALARMS of the mis-specified grep (identity is PROVEN by mode=2 presence);
a cell with neither `mode=2` nor any banner is genuinely identity-suspect -> invalid.
Do not edit the frozen runner; next family runner greps "exp752 mode=%d resolved value".

## Busy-gate lesson (for future runners; running copy left immutable)
WSL procps pgrep -f is unreliable across the argv NUL boundary and for
leading-path patterns ("bash /home/…" never matched; "/home/mfethe/exp7" didn't;
"run_exp761\.sh" did). Future busy() should /proc-scan:
  for p in $(ls /proc | grep -E '^[0-9]+$'); do
    c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
    case "$c" in *run_exp7*.sh*) case "$c" in *exp762*|"") ;; *) return 0;; esac;; esac
  done
Also: detached relaunches by other lanes are invisible to unit-based gates — check
running.json AND GPU state before launch; consider a lane convention that reruns
register in running.json immediately.
