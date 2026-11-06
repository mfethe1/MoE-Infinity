#!/usr/bin/env python3
"""exp726 frozen analysis: engine decode floor vs native HF on the same GPU."""
import json, statistics as st, sys
from pathlib import Path
D = Path(sys.argv[1]); cells = json.load(open(D.parent / "cells.json"))
A, missing = {}, []
for c in cells:
    f = D / f"{c['id']}.json"
    if not f.exists(): missing.append(c["id"]); continue
    res = json.load(open(f))
    A.setdefault((c["arm"], c["ratio"]), []).append(st.median(r["decode_tok_s"] for r in res["rows"]))
S = {}
for k, v in sorted(A.items(), key=str):
    S[k] = (st.mean(v), (st.pstdev(v) / st.mean(v)) if len(v) > 1 else float("nan"), len(v))
    print(f"{k[0]:<6} r={k[1]} n={len(v)} tok/s={S[k][0]:6.2f} cv={S[k][1]:.3f} blocks={[round(x,2) for x in v]}")
V = all(s[1] <= 0.10 for s in S.values() if s[2] == 3) and any(s[2] == 3 for s in S.values())
e75, e35, hf = S.get(("engine", 0.75)), S.get(("engine", 0.35)), S.get(("hf", None))
if e75 and hf:
    q = e75[0] / hf[0]
    H = "ENGINE-OVERHEAD-DOMINANT" if q <= 0.5 else "ENGINE-FLOOR-OK" if q >= 0.8 else "ENGINE-FLOOR-PARTIAL"
    print(f"floor ratio engine@0.75 / hf = {q:.3f}")
else:
    H = "INCOMPLETE"
if e75 and e35:
    print(f"descriptive residency gain engine@0.75 / engine@0.35 = {e75[0]/e35[0]:.3f}")
    if hf:
        t35, t75, thf = 1 / e35[0], 1 / e75[0], 1 / hf[0]
        print(f"descriptive ms/token: hf {thf*1e3:.1f} | engine@0.75 {t75*1e3:.1f} (overhead vs hf {(t75-thf)*1e3:.1f}) "
              f"| engine@0.35 {t35*1e3:.1f} (miss-driven vs @0.75 {(t35-t75)*1e3:.1f})")
print(f"\nVERDICT {'' if V else 'NOISY|'}{H} [{'COMPLETE' if not missing else f'INCOMPLETE({len(missing)} missing)'}]")
