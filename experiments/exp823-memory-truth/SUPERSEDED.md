# EXP-823 (this lane's draft) — SUPERSEDED

**Status: SUPERSEDED — do not run, freeze or register from this directory.**

The design of record for exp823 is the program's coordinator-owned pre-registration,
version 7 (`ROW14-EXP823-SECTION1-PREREGISTRATION-v7-DRAFT.md`, SHA256
`6cb6c9a0f2223ae752301e40dea0fc07128bc4a7d9a530f94365c893ad01f8d5`), confirmed by the
program's method reviewer (`ROW14-JEAN-EXP823-v7-CONFIRM.md`, SHA256
`8424ca0c299c48e2918871c9ffd29fce4c09759d6f2cfd56756dbf4f7cf8380c`). It uses the
sampler-based `own(t)` instrument (no LD_PRELOAD hook in the credit run), ratio set
0.20/0.35/0.50, a Latin-square cell order, and a four-clause OVERCOMMITTED rule.

This directory's `EXP-823-DRAFT.md` (commit `9f55f68b`) was written independently from
the C1v3 pilot evidence without knowledge of the v7 lineage. An independent method
review returned **FAIL** (2026-11-18); its findings — size-not-direction calibration,
ratio set moved off the overcommitting 0.65 arm, MiB-based tolerances, full file
pinning, missing-data rules — independently corroborate the corrections the program's
reviewer had already required across v1→v7. Both review records are archived in the
program state archive (private). Kept for the evidence trail only.
