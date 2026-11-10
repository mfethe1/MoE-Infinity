# CORRIGENDUM-759 — prose corrections from independent review (REVIEW2.md)

Sealed files (SEAL-759.md, PREREG.md, analyze759.py at commit bdcf8f2) are NOT edited. This file records corrections for all downstream use. Science unaffected; verdict unchanged.

1. **H drift sign (LOW, sole literal claim-FAIL):** SEAL-759.md prose says "H 93.87 vs seal 93.903 (+0.03)". Exact: 93.870091 − 93.903 = **−0.033** (two decimals −0.03). Gate unaffected (|−0.033| ≤ 4.0; no ENV-DRIFT is correct). Use −0.03 everywhere downstream.
2. **exp756 contrast direction (LOW):** the fresh-H effect is **H−P34 = +11.962** (equivalently P34−H = −11.962) ms/tok. Never write "P34 vs fresh H = +11.962". SEALBAR −1.949 is P34−sealed-RC, a separate comparison.
3. **Wording scope (LOW):** use "third separately measured confirmation in the same host/envelope family" (not "independent"), and "equivalent under the preregistered ±3.0 ms/tok point-estimate margin" (not "indistinguishable"). No CI was reported; this is a threshold classification. Latency reductions vs fresh H: RC 7.80%, P34 7.13% ("about 7–8%").
4. **Latent faster-label inversion (MED, not reached):** PREREG's non-equivalent branches invert direction for latency (d = P34−RC > 3.0 would mean P34 *slower*, labeled P34-FASTER). The exercised EQUIVALENT branch is correct. Future protocols must define direction-sensitive labels explicitly; do not reuse that branch text.
5. **Replay completeness (MED — CLOSED):** local out/ now includes all 10 .util.csv + 10 .load files (sizes match Winnie source). Frozen analyzer re-run locally 2026-11-10 reproduces saved verdict.txt **exactly** (EXACT MATCH, RC=0). Bundle independently replayable end-to-end.
6. **Chronology (LOW):** PREREG.md self-dates 17:0xZ vs FREEZE 16:15Z (timestamp typo). Observed prompt windows 16:23:01.68Z–16:40:15.20Z from raw JSON. Do not represent prose timestamps as verified chronology; freeze hashes match regardless.
7. **Other-GPU covariate disclosure:** RC_2/RC_3 monitor rows show foreign_other_gpu_max=1 (descriptive covariate, not gated; precell shows zero foreign compute on measured GPU at every pre-start). Disclosed in the public post.

Review provenance: REVIEW2.md (second independent reviewer, 2026-11-10; verified 9/9 freeze hashes, re-derived all medians from raw JSON, re-executed frozen verdict function via AST — exact match; leak-scan PASS for public paragraph). First reviewer (deleg_f16c6d1f) returned FAIL labels whose reasoning was unrecoverable from its log; reconciliation recorded when its result message arrives.

## Reviewer-1 reconciliation (added 2026-11-10, post-posting; sealed files untouched)

Reviewer-1 (dispatched pre-posting, delivered late) FAILed all three claims, chiefly on a HIGH defect:
"PREREG requires zero foreign GPU compute processes per cell, but RC_2/RC_3 recorded foreign_other_gpu_max=1
and were counted CLEAN."

Examined and dissolved against the family precedent the gate line itself cites
("exp746 AMENDMENT1 / exp751 / exp752 / exp756 family"):
- exp752 frozen PREREG, exclusions: "FLAGGED (foreign process on GPU1 by index or UUID, ...)" — measured-GPU scoped.
- exp752 frozen PREREG, covariates: "foreign processes on other GPUs ... are recorded per cell" — NOT excluded.
- exp759 runner (frozen run_exp759.sh line 41): `bash mon752.sh $G out/FLAGGED $ID` — watches the measured GPU (G=1).
- exp759 out/FLAGGED: ABSENT — no cell ever had foreign compute on the measured GPU.
- RC_2/RC_3 foreign_other_gpu_max=1 is GPU0 (other-GPU) activity: a recorded, disclosed covariate under family
  semantics. RC clean n=3 stands; no re-derivation; verdict admissible as sealed and posted.
Reviewer-1 lacked the exp752 directory (local-only), so its strict reading of the compressed gate wording
was reasonable in isolation but does not govern.

Reviewer-1's remaining FAILs: claim 2 rests on the dissolved gate reading plus a sign misreading of exp756
(+11.962 is H-P34; P34 was 11.962 ms/tok FASTER than fresh H — a win, direction confirmed by reviewer-2);
claims 1/3 wording items were already corrected above and the posted text uses the corrected wording.

New documentation notes from reviewer-1 (both LOW, no numeric effect):
1. PREREG.md line 57 compresses the family exclusion list to "foreign GPU compute procs = 0" without the
   measured-GPU scoping exp752 spells out. Family semantics govern; future preregs should keep the scope explicit.
2. PREREG.md line 3 timestamp is a malformed placeholder "2026-11-10T17:0xZ". Freeze provenance is carried by
   FREEZE-759.txt (16:15Z, PREREG.md sha fbc57c800549) and the freeze commit; frozen file left unchanged.
