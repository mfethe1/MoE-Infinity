# exp759 — second independent review

## Scope and bottom line

Owner/scope: second reviewer `hermes@mack/4a8bb8bf`; write only this `REVIEW2.md`. The preregistration, frozen analyzer, raw measurements, seal and upstream draft are unchanged. No upstream comment was posted. This review does not adopt the earlier review's unexplained FAIL labels.

**The frozen result supports HEAD-TO-HEAD-EQUIVALENT, both in-envelope replication labels, and absence of ENV-DRIFT.** There is no numerical basis for failing those three scientific classifications. The third admitted claim has a small, exact signed-arithmetic error in its prose: H drift is **−0.03**, not **+0.03** ms/tok. I therefore mark claim 3 **FAIL as literally printed**, while explicitly passing its envelope conclusion. Claim 2 passes as a third separately measured, same-host confirmation, not as proof of statistical independence or a third distinct admitted win.

### Verdict per claim

| Claim | Verdict | Reason |
|---|---|---|
| 1. Equivalence classification | **PASS** | Raw-data d(P34−RC) = +0.626215…; rounded to three decimals, +0.626 is inside the frozen inclusive ±3.0 bar. Parity agrees and the recorded clean engine n is 3 per arm. |
| 2. Both arms replicate; “third independent confirmation” | **PASS, with an explicit scope qualification** | RC−H = −7.320003… and P34−H = −6.693788…, both ≤ −4.10. exp752, exp756 and exp759 provide three separately measured supportive timing results in this envelope family. exp756 really did have fresh H controls; its +11.962 is **H−P34**, not P34−H. “Independent” is defensible only in the separate-measurement / separately authored implementation sense, not independent hardware, investigators or statistically independent replications. Prefer the precise replacement below. |
| 3. Drift anchors plus no ENV-DRIFT | **FAIL as written, LOW severity; envelope conclusion PASS** | Exact contradiction: the seal says `H 93.87 vs seal 93.903 (+0.03)`, but 93.87 − 93.903 = **−0.033**, and the raw-data result is −0.032909… (−0.03 at two decimals). The other signed drifts are correct. The absolute H drift remains far below 4.0, so **no ENV-DRIFT is correct**. |

The only FAIL above has an explicit numerical contradiction. A typo in a signed descriptive drift is not a failed envelope gate. The PASS qualifications distinguish frozen labels from broader statistical or causal assertions; they do not invent new post-data rejection rules.

## 1. Evidence inspected and verification boundary

Read the seven requested artifacts: `PREREG.md`, `SEAL-759.md`, `out/verdict.txt`, `out/precell.csv`, `cells759.json`, `analyze759.py`, and `DRAFT-post-nativefit.md`. Also inspected `FREEZE-759.txt`, `run_exp759.sh`, `out/RUN_SHA256`, all ten cell JSONs and their banners in the logs, and all four frozen reference JSONs. Historical checks used the sibling exp752 and exp756 `out/verdict.txt` files, exp756's preregistration including A2, and exp756's five engine-cell JSONs.

Verification performed with Python:

- All **9/9** locally available files listed with hashes in `FREEZE-759.txt` match their frozen SHA-256 values, including the preregistration, analyzer, runner, cell list and four parity references. Run-manifest entries for analyzer, runner, cells and references agree with those frozen hashes.
- Recomputed the median of `1000/decode_tok_s` across each cell's six prompt rows, then the median across cells per exp759 arm. This reproduces all reported timing medians and contrasts.
- Every engine cell has six nonempty output-id lists; all nine engine cells match all four references and hence each other. All nine engine cells record `gpu_route_effective=true`; H logs mode 0, RC logs mode 2, P34 has no mode banner.
- Executed the **unchanged original `verdict()` function**, extracted from the frozen analyzer with Python AST, on the independently recomputed measurements, verified parity, and the recorded n=3 per engine arm. Its complete verdict string matches the saved `out/verdict.txt` verdict **exactly**.

**Important replay limitation:** this local exp759 copy has **0 `*.util.csv` files and 0 `*.load` files**. Running `python3 -B analyze759.py out` therefore honestly returns `NO-UTIL` for all ten cells and `VERDICT INCONCLUSIVE(arms) H=None RC=None P34=None`. It does not reproduce the saved CLEAN verdict end to end from this incomplete local bundle. I did not fabricate telemetry, change the analyzer, or overwrite the saved verdict. The conclusions here answer the assigned question—whether the claims follow from the frozen rules and the saved analyzer output—and independently verify timing arithmetic and token parity from the available raw JSONs. Clean-cell admission, sampling counts, busy/idle split and monitor-based exclusions still rely on the saved output until the original monitor files are made available. Missing local telemetry is not evidence that the original run failed its gates.

## 2. Arithmetic recheck

All values below are ms/token. Recalculation uses full-precision JSON timings, not the two-decimal cell summaries.

| Arm | Cell medians, in execution order within arm | Median across cells | Recorded clean n |
|---|---|---:|---:|
| H | 94.013630; 93.519859; 93.870091 | **93.870091** | 3 |
| P34 | 84.145852; 87.549323; 87.176303 | **87.176303** | 3 |
| RC | 86.550088; 84.025606; 89.156094 | **86.550088** | 3 |
| hf | 30.906558 | **30.906558** | 1 |

The displayed P34 cell value `87.18` is rounded; the underlying value is `87.176303…`. Subtracting two-decimal display values is not an appropriate way to reject the saved three-decimal `+0.626` contrast.

| Quantity | Recomputed value | Rounded bar input / conclusion |
|---|---:|---|
| P34−RC | +0.626215192 | **+0.626**, absolute value ≤ 3.000: equivalent by the frozen primary rule |
| RC−H | −7.320002729 | **−7.320** ≤ −4.100: RC replicates |
| P34−H | −6.693787537 | **−6.694** ≤ −4.100: P34 replicates |
| H−93.903 | −0.032909295 | **−0.033**; absolute value ≤ 4.0: H consistency gate passes |
| RC−85.699 | +0.851087976 | **+0.851**; inside report-only ±3.0 |
| P34−85.699 | +1.477303168 | **+1.477**; inside report-only ±3.0 |
| hf−31.791 | −0.884441818 | **−0.884**; inside informational ±3.0, n=1 |

Latency reductions relative to fresh H are **7.798% for RC** and **7.131% for P34**. “About 7–8% lower decode latency” is more precise than implying that each arm has an exactly 8% reduction. This is latency reduction, not an identically sized percentage increase in tokens/second.

**Arithmetic assessment:** frozen analyzer values and classifications are correct for these inputs. The as-written seal's signed H drift is not correct; consequently an all-prose-inclusive `arithmetic_ok` must be **false**, solely because of that sign error. The gate outcomes are unaffected.

## 3. Claim 1 — equivalence classification: PASS

Frozen evidence, `PREREG.md:61–64`:

> “Frozen bars (THR = 3.0 ms/tok, exp752 continuity; comparisons rounded to 3 dp before bars)”
>
> “**PRIMARY (head-to-head):** d = median(P34 clean) − median(RC clean).”
>
> “|d| ≤ 3.0 → **HEAD-TO-HEAD-EQUIVALENT**”

The saved output reports:

> `VERDICT HEAD-TO-HEAD-EQUIVALENT d(P34-RC)=0.626 THR=3.0`

The independently recomputed contrast is +0.626215…, which is unambiguously inside the inclusive frozen bar. There is no requirement in the frozen rule for a confidence interval, a significance test, or non-overlapping cell ranges. Requiring any of those now would change the preregistered endpoint after seeing the data.

**Wording boundary:** “equivalent within the preregistered 3.0 ms/tok point-estimate margin in this run” is supported. “Indistinguishable decode speed” should not be read as proof of population equivalence, exact equality, or a formal confidence-interval equivalence test. With three cells per engine arm and one fixed execution order, no confidence interval is reported in the provided analysis. State that limitation rather than fabricate one.

**Latent frozen-rule defect, not a failure of this result:** the rest of `PREREG.md:64` says:

> “d > 3.0 → **P34-FASTER**; d < −3.0 → **RC-FASTER**.”

Those directional labels are reversed for latency when d=P34−RC; positive d would make P34 slower. The analyzer duplicates that inversion. An isolated call to the original function with d=+4 produces `P34-FASTER`, confirming the issue. Neither directional branch is reached here, so it cannot contradict or invalidate the actual **HEAD-TO-HEAD-EQUIVALENT** classification. Preserve the frozen files; disclose the latent error and correct it prospectively rather than silently changing the frozen endpoint.

## 4. Claim 2 — both replicate; historical confirmation wording: PASS with scope

Frozen evidence, `PREREG.md:65–66`:

> “**SECONDARY replication:** RC−H ≤ −4.10 → **RC-REPLICATED-IN-ENVELOPE** (0.5× sealed −8.20);”
>
> “P34−H ≤ −4.10 → **P34-REPLICATED-IN-ENVELOPE**.”

Saved output:

> `RC-REPLICATED-IN-ENVELOPE[RC-H=-7.32] P34-REPLICATED-IN-ENVELOPE[P34-H=-6.69]`

Both inequalities pass, as does token parity against both H references and both RC references. Nothing in the frozen secondary rule requires either implementation to win the head-to-head contest or to be separated from the other implementation by 3 ms/token. Equivalence between the two candidates and replication of each candidate's win over H are fully compatible statements.

### What exp752 and exp756 actually establish

1. **exp752:** saved output reports `TOTAL RC-H = -8.20 ms/tok`. Its original saved output also says `PARITY H-self-consistent=False R=NA RC=NA` and labels its timing verdicts `PARITY-NA`. Do not retrospectively advertise exp752 as having passed exp759's stronger parity rule. That historical saved-output caveat does not negate its reported timing direction; this review independently verifies that the four references currently frozen for exp759 agree.
2. **exp756:** its primary endpoint is explicitly fresh-H controlled. `PREREG.md:67` says:

   > “**Primary (matched-window):** Δ = fresh_H − P34 (medians of clean cells), ms/tok.”

   Amendment A2 subsequently and explicitly changes the across-cell aggregation to **mean of clean cells**, maintaining the per-cell median. Recomputing its actual raw inputs with that frozen amended convention gives fresh H **95.712224643** and P34 **83.750423018**. Thus **H−P34 = +11.961801626**, or +11.962; equivalently **P34−H = −11.962**. Its output explicitly says:

   > `TOTAL H-P34 = +11.96 ms/tok`
   >
   > `VERDICT REPLICATED`

   The separate `SEALBAR P34 ... = -1.95` is P34−sealed RC, **not its only comparison and not its fresh-H effect**. Dismissing exp756 as merely a cross-run sealed-baseline comparison would be factually wrong.
3. **exp759:** both fresh-H contrasts pass the new frozen replication bar in the same interleaved envelope, as calculated above.

**A sign-description defect in exp759's historical summary:** `PREREG.md:13` literally says:

> “exp756 measured P34 vs fresh H = +11.962 ms/tok in this same envelope family (SEALBAR P34 vs sealed RC = −1.949).”

If “P34 vs fresh H” denotes P34−H, that positive sign contradicts the historical raw data. Preserve the literal source wording in the review, but do not propagate it: explicitly name the contrast **fresh H−P34 = +11.962**, or **P34−fresh H = −11.962**. The genuine fresh-H speedup is supported; treating that ambiguous prose as a measured +11.962 latency regression would contradict exp756's actual output.

### Is “third independent confirmation” supported?

**Yes as a third separately collected same-host timing confirmation, not as a strong independence claim.** The three experiments above contain distinct measurements supporting the event-poll-retirement plus completion-queue approach over the H callback baseline. Two separately authored implementations now show the benefit in one matched session. The sealed-RC comparison in exp756 does not replace or erase its fresh-H comparison.

**Not established:** independence across GPUs/hosts, workloads, investigators, build lineage or statistical errors. The experiments reuse the host/envelope and some builds and references. Nor should “third confirmation” become “third distinct admitted win”: exp756's preregistration expressly says (`:82–85`):

> “Replication claims limited to OLMoE-1B-7B-0125-Instruct + lcnu 0.75 + this host; no claim beyond OLMoE/this envelope. A single-window replication of an upstream head is evidence for the sealed effect transferring to their code, not a new distinct admitted win beyond exp752's #77 record unless the coordinator decides otherwise.”

That sentence limits generalization and win accounting; it does **not** contradict a third same-host confirmation. There is no valid quoted numerical contradiction for rejecting the three-confirmation count. I therefore do not issue a FAIL on that count. Replace the ambiguous adjective rather than overclaim independence:

> “This is a third separately measured confirmation in the same host/envelope family (exp752, exp756 and exp759), now with both implementations compared against the same fresh H controls.”

Attribution should remain to the combined implementation lever, not proof that polling retirement alone accounts for all of the gain: exp752's own R-only comparison was `RETIRE R-H = -2.92` and its larger total comparison was RC−H = −8.20.

## 5. Claim 3 — anchors and no ENV-DRIFT: literal sign FAIL, gate PASS

Exact offending sentence, `SEAL-759.md:34–35`:

> “Drift anchors: H 93.87 vs seal 93.903 (+0.03); RC 86.55 vs 85.699 (+0.85); P34 87.18 vs 85.699 (+1.48); hf 30.91 vs 31.791 (-0.88, informational n=1). Envelope valid (no ENV-DRIFT suffix).”

**Exact numerical contradiction:** `93.87 − 93.903 = −0.033`, not `+0.03`. Using the unrounded measured H median yields −0.032909…, also negative. Replace only the signed prose value with **−0.03**; no timing rerun or new exclusion is warranted by that typo.

The controlling frozen sentence, `PREREG.md:70–73`, is:

> “**Consistency:** |fresh H − 93.903| ≤ 4.0 **gates the envelope** (violation → verdict suffix `ENV-DRIFT`, all timing labels become descriptive); |RC − 85.699| ≤ 3.0 and |P34 − 85.699| ≤ 3.0 are **reported only** (the head-to-head delta is robust to shared drift by design; a seal miss on one arm alone is a finding, not an automatic fail); |hf − 31.791| ≤ 3.0 informational at n=1.”

Here |H−seal| = 0.032909… ≤ 4.0. RC and P34 are also inside their report-only bars, and hf is inside its informational bar. There is no ENV-DRIFT trigger. **P34's consistency anchor is sealed RC 85.699 by explicit preregistration, not exp756 P34 83.750.** Using 83.750 as an automatic gate would change both the chosen anchor and its report-only status. It is not permitted as a reason to fail this claim.

The two `foreign_other_gpu_max=1` rows in the saved verdict (RC_2 and RC_3) should remain disclosed. They are not, on their own, proof of a foreign process on the measured GPU. The frozen analyzer reads this monitor field as a descriptive covariate and does not gate on it; the runner/monitor uses separate contamination flags. `out/precell.csv` records zero foreign-compute count, zero loaded Ollama models and zero runner workers at every cell's pre-start sample, with GPU memory below 1024 MiB. The leading `1 QUIET` for RC_1 is part of its quiet-wait result, not evidence of a foreign GPU process. Do not manufacture a new other-GPU exclusion after the fact. Because the local load/util files are missing, I cannot independently exclude transient target-GPU contamination from those monitors; that remains the replay limitation stated above, not an observed contradiction of the saved admission decision.

## 6. Provenance nits and actions

These observations do not change the frozen thresholds or the actual head-to-head result:

- **LOW — signed H drift typo:** correct `+0.03` to `−0.03` in an explicit seal erratum. This is the sole literal claim FAIL.
- **LOW — historical contrast direction:** exp759's summary must name the exp756 contrast as H−P34 = +11.962 (or P34−H = −11.962), rather than leave “P34 vs fresh H = +11.962” ambiguous.
- **LOW — “independent” and “indistinguishable” wording:** replace with separately measured same-host confirmation and equivalence under the preregistered point-estimate margin. These are scope/precision corrections, not evidence that either replication inequality failed.
- **MED — latent faster-label inversion:** the frozen non-equivalent branches reverse faster/slower direction for latency. Record an erratum and repair future protocol versions; do not retroactively alter this frozen experiment. The equivalence branch actually exercised is correct.
- **MED — replay completeness:** preserve/copy the original ten load files and ten utilization CSVs, plus original contamination/failure records or an explicit record of their absence, if publication requires independently replayable gate admission. Re-run the unchanged analyzer on that complete bundle. Current raw timing/parity checks and exact verdict-function replay do not replace those monitor records.
- **LOW — chronology text:** `PREREG.md:3` says `Pre-registered 2026-11-10T17:0xZ`, while `FREEZE-759.txt:1` says `2026-11-10T16:15Z`, and raw JSON prompt windows range from **16:23:01.676540Z through 16:40:15.197239Z**. The seal's run summary ends at `16:39Z`. The freeze hashes match, but a self-dated text file alone does not independently prove pre-data publication, and these prose timestamps should not be represented as a verified chronology. Preserve the freeze, explain the timestamp typo with the original launch/freeze receipt, and use the raw timestamps for the observed prompt-window bound. Do not silently edit the frozen preregistration or claim that this proves post-data amendment.

No frozen file was changed to resolve any of these findings.

## 7. Proposed final paragraph for the upstream post

> In a single interleaved WSL2 session on an RTX 5060 Ti 16GB (OLMoE-1B-7B-0125-Instruct, lcnu, offload ratio 0.75), median decode latency was 93.870 ms/token for the callback control, 86.550 for #353 and 87.176 for #354, with three cells per engine arm. The #354−#353 difference was +0.626 ms/token: equivalent under our preregistered ±3.0 ms/token point-estimate margin. This is a threshold classification, not a confidence-interval equivalence test; no confidence interval is reported. Both implementations cleared the preregistered in-envelope replication bar against the fresh control (−7.320 and −6.694 ms/token, about 7–8% lower latency). All nine engine cells produced token IDs identical to each other and to the frozen references, and the fresh-control drift gate passed. This is a third separately measured confirmation in the same host/envelope family, now comparing both implementations against the same fresh controls; it does not establish a speed winner between the two PRs or generalize beyond this workload. Two #353 cells recorded other-GPU activity in the saved monitor summary; that covariate is disclosed and was not an exclusion under the frozen analyzer.

The paragraph reports the saved clean-run result subject to the explicit local replay limitation above. It does not certify the draft's separate native-Linux memory-headroom findings; exp751/exp755 data are outside this delegated review. In particular, this paragraph does not imply that WSL2 ratio-0.75 timing results are a native-Linux ratio-0.60 head-to-head benchmark.

## 8. Leak scan and publication boundary

**PASS for the existing upstream draft and the proposed paragraph.** Applied local pattern checks for private-key blocks, common provider/GitHub credential formats, assigned secret values, email addresses, RFC1918/tailnet IPv4 addresses, private home-directory paths and internal fleet hostnames. The current `DRAFT-post-nativefit.md` has **no matches** in those categories. The proposed paragraph uses public PR numbers, workload/hardware descriptions and benchmark results; it contains no credentials, private paths, internal hostnames, rental offer/instance/account identifiers, private endpoints, personal contact data or raw generated token text. Final artifact verification scans the proposed paragraph extracted from this review as well.

**Do not interpret this as approval to publish the entire internal evidence bundle.** `PREREG.md` contains private build/home paths and the internal machine nickname; `SEAL-759.md` also names the internal machine. Raw environment/manifest files include private paths and can include further machine identifiers. This review is internal and quotes some internal provenance; it is not the public post. Export only a deliberately redacted public evidence bundle. No external upload or post occurred.

The scan is scoped to concrete textual identifiers and credential patterns, not an assertion that all internal artifacts are safe or that native-memory claims have been independently validated.
