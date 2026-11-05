# exp715 LEDGER — engine eviction-policy port parity on 3 real traces
- 2026-11-05 build: pinned upstream port + simulator copied unmodified (SOURCE.sha256); own timing driver; smoke OK (smoke.log; reduced, NOT a result).
- 2026-11-05 09:55 EST settled: PARITY-HOLDS:DEFAULT-CHALLENGED|OVERHEAD-OK. P1 351/351 exact + det; P2 27/27 == sealed exp704; P3 FAIL 17/27 (LCNU loses to S3-FIFO in the upper capacity tail of every trace, worst 3.27pp lo@2048); P4 LCNU <=685 ns/access. ADDENDUM58 (independent adjudicator, 390 checks).
