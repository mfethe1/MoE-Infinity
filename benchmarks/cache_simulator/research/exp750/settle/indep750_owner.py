#!/usr/bin/env python3
"""exp750 owner independent recompute from raw cell JSONs (does NOT import classify750).
Recomputes per-cell D/E from raw t1/t64, quality vs ref (out_ids, top16_ids, top16_vals), timed identity,
then D1/D2/D3 ratios using the classifier's cell-of-record choices (passed explicitly below, taken from
class750.txt REPLACED-BY lines). Prints a compact table; exit 1 on any disagreement with class750.txt D values."""
import json, re, statistics, sys
from pathlib import Path
out = Path(sys.argv[1]); ref = json.load(open(sys.argv[2]))
cls = (out / 'class750.txt').read_text()
sealed = {m.group(1): float(m.group(2)) for m in re.finditer(r'^(\w+): present=True .*? D=([0-9.]+)', cls, re.M)}
sealed.update({m.group(1): float(m.group(2)) for m in re.finditer(r'REPLACED-BY (\w+) \(D=([0-9.]+)\)', cls)})
bad = 0; res = {}
for f in sorted(out.glob('b*_*.json')):
    if f.name.endswith('.prov.json'): continue
    cid = f.stem; d = json.load(open(f)); dp = []; ep = []; q = 0; tid = True
    for r, rr in zip(d['rows'], ref['rows']):
        q += (r['out_ids'] == rr['out_ids'] and r['top16_ids'] == rr['top16_ids'] and r['top16_vals'] == rr['top16_vals'])
        ds = [(t['t64_s'] - t['t1_s']) / 63 * 1000 for t in r['timed']]
        es = [t['t64_s'] / 64 * 1000 for t in r['timed']]
        tid &= all(t['out_ids_64'] == r['out_ids'] for t in r['timed'])
        dp.append(statistics.median(ds)); ep.append(statistics.median(es))
    D = statistics.median(dp); E = statistics.median(ep); res[cid] = D
    agree = (abs(sealed[cid] - D) < 1e-9) if cid in sealed else 'not-printed'
    bad += (agree is False)
    print(f'{cid:10s} D={D:8.2f} E={E:8.2f} quality={q}/6 timed_identity={tid} sealed_agree={agree}')
rec = {'R1': ['b1_R1_x', 'b2_R1', None], 'S1': ['b1_S1', 'b2_S1', 'b3_S1_x'], 'P2': ['b1_P2', 'b2_P2', 'b3_P2'],
       'K2': ['b1_K2', 'b2_K2_x', 'b3_K2'], 'S0': ['b1_S0', 'b2_S0', 'b3_S0_x'], 'C2': ['b1_C2', 'b2_C2', 'b3_C2'],
       'H2': ['b1_H2', 'b2_H2', 'b3_H2']}
g = lambda a, b: res[rec[a][b]] if rec[a][b] else None
for name, (num, den) in {'D1 K2/P2': ('K2', 'P2'), 'D2 S1/R1': ('S1', 'R1'), 'D3 S1/P2': ('S1', 'P2'),
                         'link S0/S1': ('S0', 'S1'), 'C2/P2 (corrupt vs fix)': ('C2', 'P2'), 'P2/H2': ('P2', 'H2'),
                         'S1/H2': ('S1', 'H2')}.items():
    print(name, [round(g(num, b) / g(den, b), 4) if g(num, b) and g(den, b) else None for b in range(3)])
print('DISAGREEMENTS', bad); sys.exit(1 if bad else 0)
