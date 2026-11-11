# exp767 armaments provenance

- REPAIR-DESIGN.md + patched/ : t3 (codex/gpt-6.1-sol) micro-patch for prereg branch D2 (python>=0.70).
- TRANSFER-DESIGN.md : t3 design for branch D1 (native>=0.70).
- VERDICT D5 NULL-TIME retired both: measured python self-time 0.09s, subtree total +1.88s < tau.
- The +7.8s unprofiled wall cost (exp763) migrates via the eager dispatch path (exp764), not the prefetcher subtree.
