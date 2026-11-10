# exp759 SEALED 2026-11-10T16:43Z
Run: 2026-11-10T16:22:17Z - 16:39Z (envelope incl. build 16:16Z), Winnie GPU1, all 10 cells CLEAN, 0 FLAGGED, 0 FAILED.
Binary provenance: RC753 _store f54e5756... (built from PR #353 head b7f6ca4d2caa5229698d78deb03b454fc20947dd),
H _store 95da1b70... (sealed exp752), P34 _store ffbed79a... (PR #354 head 827019db, exp756 build).
Identity gates passed (three arms import from private trees; banner modes H=0 RC=2; P34 banner-absent).
Parity: all engine clean cells byte-identical to sealed refs (H_2/H_3/RC_2/RC_3 agree).

cell hf_1: arm=hf ms/tok=30.91 busy=14.17 idle=16.77 load_mean=1.76 foreign_other_gpu_max=0 CLEAN
cell H_1: arm=H ms/tok=94.01 busy=39.98 idle=54.53 load_mean=1.28 foreign_other_gpu_max=0 CLEAN
cell P34_1: arm=P34 ms/tok=84.15 busy=38.54 idle=45.95 load_mean=1.26 foreign_other_gpu_max=0 CLEAN
cell RC_1: arm=RC ms/tok=86.55 busy=39.80 idle=45.88 load_mean=1.29 foreign_other_gpu_max=0 CLEAN
cell H_2: arm=H ms/tok=93.52 busy=38.42 idle=56.47 load_mean=1.39 foreign_other_gpu_max=0 CLEAN
cell P34_2: arm=P34 ms/tok=87.55 busy=39.29 idle=47.85 load_mean=1.38 foreign_other_gpu_max=0 CLEAN
cell RC_2: arm=RC ms/tok=84.03 busy=39.09 idle=45.98 load_mean=1.38 foreign_other_gpu_max=1 CLEAN
cell H_3: arm=H ms/tok=93.87 busy=39.70 idle=55.66 load_mean=1.46 foreign_other_gpu_max=0 CLEAN
cell P34_3: arm=P34 ms/tok=87.18 busy=39.99 idle=47.10 load_mean=1.38 foreign_other_gpu_max=0 CLEAN
cell RC_3: arm=RC ms/tok=89.16 busy=40.47 idle=47.04 load_mean=1.13 foreign_other_gpu_max=1 CLEAN

parity: OK all engine clean cells byte-identical to sealed refs
arm H: median=93.87 clean n=3
arm RC: median=86.55 clean n=3
arm P34: median=87.176 clean n=3
arm hf: median=30.907 clean n=1
drift hf: 30.91 vs seal 31.791 [ok] (informational n=1)

VERDICT HEAD-TO-HEAD-EQUIVALENT d(P34-RC)=0.626 THR=3.0 | RC-REPLICATED-IN-ENVELOPE[RC-H=-7.32] P34-REPLICATED-IN-ENVELOPE[P34-H=-6.69] | H=93.87 vs seal 93.903 [ok] RC=86.55 vs seal 85.699 [ok] P34=87.18 vs seal 85.699 [ok]

Admitted claims:
1. d(P34-RC)=+0.626 ms/tok, |d|<=3.0 -> HEAD-TO-HEAD-EQUIVALENT. PR #353 (ours, +99/-2) and PR #354
   (upstream, +278/-204) deliver indistinguishable decode speed in one interleaved envelope on the same host.
2. RC-H=-7.32, P34-H=-6.69 (bar <=-4.10): the ~7 ms/tok (~8 pct) event-poll win over host-callback
   replication appears in BOTH independent implementations. Third independent confirmation (exp752, exp756,
   exp759) of the engine_overhead lever.
3. Drift anchors: H 93.87 vs seal 93.903 (+0.03); RC 86.55 vs 85.699 (+0.85); P34 87.18 vs 85.699 (+1.48);
   hf 30.91 vs 31.791 (-0.88, informational n=1). Envelope valid (no ENV-DRIFT suffix).
NOTE: RC_2/RC_3 precell recorded foreign_other_gpu_max=1 (transient non-engine GPU proc at sample time);
analyzer (frozen pre-data) does not gate on it; parity + all drift anchors hold, so verdict unaffected.
Analyzer behaviorally verified pre-freeze on 3 synthetic fixtures (EQUIVALENT / PARITY-FAIL / INCONCLUSIVE).
