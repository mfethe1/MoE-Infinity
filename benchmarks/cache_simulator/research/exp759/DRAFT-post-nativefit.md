# DRAFT — upstream post (NOT posted; awaiting exp759 head-to-head outcome for the final paragraph)
# Target: PR #353 (retire-by-event) and/or PR #354 discussion — memory-headroom context both need
# Status: draft 2026-11-10; posting approved in principle; final numbers to be filled from exp759

We measured the practical GPU-memory headroom this dispatcher work needs on both platforms while benchmarking #353/#354 (OLMoE-1B-7B-0125-Instruct, lcnu 0.75, 6-prompt greedy decode):

- WSL2 (RTX 5060 Ti 16GB): offload ratio up to **0.75** loads and decodes cleanly (our sealed exp752 envelope).
- Native Linux (rental RTX 5060 Ti 16GB, cuda 12.8.1): **0.75 / 0.70 / 0.65 all OOM at load**; **0.60** is the clean fit (6/6 prompts, 16.5–19.7 tok/s decode, 0 OOM hits, rc=0). Replicated across three separate host offers with the same OOM ladder; measurement scripts: `ladder755.sh` (dynamic `ROWS>=N(prompts)` bar).

Takeaway for reviewers: memory headroom on native Linux is materially tighter than on WSL for the same GPU — a ~20% lower offload ratio (0.60 vs 0.75) is the safe operating point. Any evaluation of #353 vs #354 should pin the ratio per-platform rather than reusing WSL-tuned values.

[FINAL PARAGRAPH — fill after exp759: head-to-head d = median(P34) − median(RC) with CI treatment, parity statement, and which PR's approach wins or that they are equivalent within 3.0 ms/tok.]

Provenance: exp751/exp755 (native), exp752 (sealed WSL envelope), exp759 (head-to-head, prereg frozen pre-data).
