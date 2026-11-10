# FINAL — upstream post (ready; held one turn for reviewer-1 reason reconciliation)
# Target: PR #353 (retire-by-event) and/or PR #354 discussion — memory-headroom context both need
# Status: finalized 2026-11-10 per REVIEW2.md (leak-scan PASS; corrigendum applied)

We measured the practical GPU-memory headroom this dispatcher work needs on both platforms while benchmarking #353/#354 (OLMoE-1B-7B-0125-Instruct, lcnu 0.75, 6-prompt greedy decode):

- WSL2 (RTX 5060 Ti 16GB): offload ratio up to **0.75** loads and decodes cleanly (our sealed exp752 envelope).
- Native Linux (rental RTX 5060 Ti 16GB, cuda 12.8.1): **0.75 / 0.70 / 0.65 all OOM at load**; **0.60** is the clean fit (6/6 prompts, 16.5–19.7 tok/s decode, 0 OOM hits, rc=0). Replicated across three separate host offers with the same OOM ladder; measurement scripts: `ladder755.sh` (dynamic `ROWS>=N(prompts)` bar).

Takeaway for reviewers: memory headroom on native Linux is materially tighter than on WSL for the same GPU — a ~20% lower offload ratio (0.60 vs 0.75) is the safe operating point. Any evaluation of #353 vs #354 should pin the ratio per-platform rather than reusing WSL-tuned values.

In a single interleaved WSL2 session on an RTX 5060 Ti 16GB (OLMoE-1B-7B-0125-Instruct, lcnu, offload ratio 0.75), median decode latency was 93.870 ms/token for the callback control, 86.550 for #353 and 87.176 for #354, with three cells per engine arm. The #354−#353 difference was +0.626 ms/token: equivalent under our preregistered ±3.0 ms/token point-estimate margin. This is a threshold classification, not a confidence-interval equivalence test; no confidence interval is reported. Both implementations cleared the preregistered in-envelope replication bar against the fresh control (−7.320 and −6.694 ms/token, about 7–8% lower latency). All nine engine cells produced token IDs identical to each other and to the frozen references, and the fresh-control drift gate passed. This is a third separately measured confirmation in the same host/envelope family, now comparing both implementations against the same fresh controls; it does not establish a speed winner between the two PRs or generalize beyond this workload. Two #353 cells recorded other-GPU activity in the saved monitor summary; that covariate is disclosed and was not an exclusion under the frozen analyzer.

Provenance: exp751/exp755 (native), exp752 (sealed WSL envelope), exp759 (head-to-head, prereg frozen pre-data).
