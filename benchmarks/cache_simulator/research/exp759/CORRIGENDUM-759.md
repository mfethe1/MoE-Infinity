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
