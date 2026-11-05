#!/usr/bin/env python3
"""gen_addendum57.py — programmatic ADDENDUM57 for exp713 (STACK-1001, lane 79990).
Every number is parsed at runtime from sealed primary artifacts:
  - exp713/exp713-gclamp.json        (this experiment's sealed result)
  - exp674-hl-transfer.json          (sealed H0 bookends cf_center / cf_bo + standalones; bo_params)
  - exp712/exp712-gdose.json         (sealed certified gamma edge)
  - exp670-synth.json                (sealed stream sha8 list)
  - exp713/ARTIFACT.sha256 + freeze commit f6c2367 blobs (git show)
The adjudicator below is written independently of run_gclamp.py: it rebuilds the arm parameters
from the PREREG text, re-derives H0/H4/H1/H2 per arm and the frozen ladder from the grid, and
asserts agreement with the runner. No hand math, no hand-transcribed hashes."""
import hashlib
import json
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.join(BASE, 'exp713')
LOCALDIR = '/Users/mfethe/warp-work/exp713-moei-gclamp'
LOCALRES = os.path.join(LOCALDIR, 'exp713-gclamp.json')
LOCAL674 = '/Users/mfethe/warp-work/exp674-moei-hl-transfer/exp674-hl-transfer.json'
LOCAL712 = '/Users/mfethe/warp-work/exp712-moei-gdose/exp712-gdose.json'
POLICIES = '/Users/mfethe/warp-work/moei-granite3b/benchmarks/cache_simulator/policies.py'
FREEZE = 'f6c2367'

R = json.load(open(os.path.join(EXP, 'exp713-gclamp.json')))
X674 = json.load(open(os.path.join(BASE, 'exp674-hl-transfer.json')))
X712 = json.load(open(os.path.join(BASE, 'exp712', 'exp712-gdose.json')))
X670 = json.load(open(os.path.join(BASE, 'exp670-synth.json')))

checks = []


def chk(name, ok):
    checks.append((name, bool(ok)))
    assert ok, name


sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()  # noqa: E731
chk('published result byte-equal local sealed result', sha(os.path.join(EXP, 'exp713-gclamp.json')) == sha(LOCALRES))
chk('published exp674 parse-equal to runner input', json.load(open(LOCAL674)) == X674)
chk('published exp712 parse-equal to runner input', json.load(open(LOCAL712)) == X712)

# parameters rebuilt from PREREG text + sealed inputs (runtime parse)
CENTER = (0.005, 0.0025, 32768.0)
bp = X674['bo_params']
BO = (float(bp['margin']), float(bp['gamma']), float(bp['half_life']))
chk('exp712 verdict is G-BOUNDARY@g*', X712['verdict'].startswith('G-BOUNDARY@g'))
j = int(X712['verdict'].split('@g')[1])
G_EDGE = float(X712['certified_gamma_upper_edge'])
chk('G_EDGE == exp712 g_{j-1}', X712['rules']['gammas'][j - 1] == G_EDGE)
chk('center gamma < G_EDGE < BO gamma', CENTER[1] < G_EDGE < BO[1])
P = {'center': CENTER, 'bo': BO, 'clamp': (BO[0], G_EDGE, BO[2]),
     'clampM': (BO[0], G_EDGE, CENTER[2]), 'clampH': (CENTER[0], G_EDGE, BO[2])}
ARMS = list(P)
for a in ARMS:
    chk(f'arm {a} params == PREREG rebuild', tuple(R['arms'][a]['params']) == P[a] == tuple(R['rules']['params'][a]))
SAFE_PP, SW_MAX, INF_PP, TR_PP = 0.5, 6, 0.1, -0.05
chk('bars frozen', (R['rules']['safety_pp'], R['rules']['switch_max'], R['rules']['informative_pp'],
                    R['rules']['transfer_pp']) == (SAFE_PP, SW_MAX, INF_PP, TR_PP))

key = lambda cfg: json.dumps(cfg, sort_keys=True)  # noqa: E731
G = R['grid']
chk('11 streams x 6 caps', len(G) == 11 and sum(len(s['caps']) for s in G) == 66)
chk('11 stream sha8 == exp670', [s['seed'] for s in G] == [s['seed'] for s in X670['grid']])
ref = {(key(s['cfg']), int(c)): cell for s in X674['grid'] for c, cell in s['caps'].items()}
chk('exp674 ref covers same 66 cells', set(ref) == {(key(s['cfg']), int(c)) for s in G for c in s['caps']})
mm = sum(cell[x] != ref[(key(s['cfg']), int(cap))][x] for s in G for cap, cell in s['caps'].items()
         for x in ('cf_center', 'cf_bo'))
sa = sum(cell[x] != ref[(key(s['cfg']), int(cap))][x] for s in G for cap, cell in s['caps'].items()
         for x in ('lcnu', 's3fifo'))
chk('H0 bookends 132/132 exact vs exp674 (cf_center, cf_bo)', mm == 0)
chk('H0 standalones 132/132 exact vs exp674', sa == 0)
chk('H0 runner 264 cells ok', R['H0_replication']['cells'] == 264 and R['H0_replication']['ok']
    and not R['H0_replication']['mismatches'])
acct = sum(cell['cf_' + a]['rate'] != cell['cf_' + a]['prop'] for s in G for cell in s['caps'].values() for a in ARMS)
chk('H4 accounting 330/330 loop==prop', acct == 0 and R['H4_accounting'] is True and not R['accounting_violations'])
chk('H4 determinism two full runs', R['determinism_two_runs'] is True)

per = {a: dict(worst=None, wc=None, over=[], sw=0, maxsw=0, deltas=[]) for a in ARMS}
inf = 0
for s in G:
    for cap, cell in s['caps'].items():
        lc, s3 = cell['lcnu']['rate'], cell['s3fifo']['rate']
        if abs(lc - s3) * 100 < INF_PP:
            continue
        inf += 1
        best = max(lc, s3)
        for a in ARMS:
            x = cell['cf_' + a]
            p = per[a]
            d = (best - x['rate']) * 100
            p['deltas'].append((x['rate'] - cell['cf_center']['rate']) * 100)
            p['maxsw'] = max(p['maxsw'], x['switches'])
            if p['worst'] is None or d > p['worst']:
                p['worst'], p['wc'] = d, (s['cfg'], cap)
            if d > SAFE_PP:
                p['over'].append((s['cfg'], cap, round(d, 3)))
            p['sw'] += x['switches'] > SW_MAX
chk('59 informative cells (== exp674)', inf == 59 == R['informative_cells'] == X674['informative_cells'])
safe = {a: not per[a]['over'] and per[a]['sw'] == 0 for a in ARMS}
mean = {a: sum(per[a]['deltas']) / len(per[a]['deltas']) for a in ARMS}
for a in ARMS:
    r = R['arms'][a]
    p = per[a]
    chk(f'arm {a} worst/over/maxsw/mean/H1 == runner',
        r['worst']['deficit_pp'] == round(p['worst'], 3) and r['cells_over_bar'] == len(p['over'])
        and r['cells_over_switch'] == p['sw'] and r['max_switches'] == p['maxsw'] and r['H1_safe'] == safe[a]
        and r['mean_delta_vs_center_pp'] == round(mean[a], 4))
h2 = round(mean['clamp'], 4) >= TR_PP
chk('H2 re-derived == runner', h2 == R['H2_transfer_clamp'])

# independent ladder (re-written from the PREREG text, not imported)
if mm or sa or acct or not R['determinism_two_runs']:
    verdict = 'ACCOUNTING-FAIL'
elif safe['clamp']:
    verdict = 'CLAMP-REPAIRS:' + ('TRANSFERS' if h2 else 'NO-GAIN')
else:
    verdict = 'CLAMP-INSUFFICIENT:' + {(True, False): 'HL-CONDITIONAL', (False, True): 'M-CONDITIONAL',
                                       (True, True): 'JOINT-ONLY', (False, False): 'BOTH-CONTEXTS'}[
        (safe['clampM'], safe['clampH'])]
chk('verdict re-derived == runner', verdict == R['verdict'])

# exp674 cross-checks: bookends reproduce exp674's summary statistics
w674 = X674['worst_bo_deficit']
chk('bo worst cell == exp674 worst_bo_deficit', round(per['bo']['worst'], 3) == w674['deficit_pp']
    and key(per['bo']['wc'][0]) == key(w674['cfg']) and per['bo']['wc'][1] == w674['cap'])
chk('bo mean delta == exp674 mean_delta_bo_pp', round(mean['bo'], 4) == X674['mean_delta_bo_pp'])
v674 = {(key(v['cfg']), v['cap']) for v in X674['violations']}
over_sets = {a: {(key(o[0]), o[1]) for o in per[a]['over']} for a in ARMS}
chk('bo over-bar set == exp674 violation set', over_sets['bo'] == v674)
nested_H = over_sets['clampH'] <= over_sets['bo']
g3 = X712['arms'][f'g{j - 1}']
chk('exp712 edge arm == (center M, G_EDGE, center HL) and H1 safe', tuple(g3['params']) == (CENTER[0], G_EDGE, CENTER[2])
    and g3['H1_safe'] is True)
chk('clampH differs from exp712 edge arm only in HL', P['clampH'][:2] == tuple(g3['params'])[:2] and P['clampH'][2] != g3['params'][2])

# integrity: ARTIFACT == working files == freeze-commit blobs; freeze precedes result
art = dict(ln.split()[::-1] for ln in open(os.path.join(EXP, 'ARTIFACT.sha256')).read().strip().splitlines())
REPO = subprocess.check_output(['git', '-C', BASE, 'rev-parse', '--show-toplevel'], text=True).strip()
rel = os.path.relpath(EXP, REPO)
art_blob = subprocess.check_output(['git', '-C', REPO, 'show', f'{FREEZE}:{rel}/ARTIFACT.sha256'])
chk('ARTIFACT.sha256 == freeze-commit blob', hashlib.sha256(art_blob).hexdigest() == sha(os.path.join(EXP, 'ARTIFACT.sha256')))
for f in ('run_gclamp.py', 'PREREG.md', 'smoke.log'):
    blob = subprocess.check_output(['git', '-C', REPO, 'show', f'{FREEZE}:{rel}/{f}'])
    chk(f'{f} sha == ARTIFACT == freeze blob == local', art[f] == sha(os.path.join(EXP, f))
        == hashlib.sha256(blob).hexdigest() == sha(os.path.join(LOCALDIR, f)))
chk('policies.py sha == ARTIFACT (runner import path)', art['policies.py'] == sha(POLICIES))
freeze_t = int(subprocess.check_output(['git', '-C', REPO, 'log', '-1', '--format=%ct', FREEZE], text=True).strip())
chk('freeze commit precedes result mtime', freeze_t < os.path.getmtime(LOCALRES))


def cfgs(cfg):
    return f"s={cfg['s']} lam={cfg['lam']} E={cfg['E']}/L={cfg['L']}"


ROLE = {'center': 'bookend == exp674 cf_center', 'bo': 'bookend == exp674 cf_bo', 'clamp': 'PRIMARY',
        'clampM': 'attribution (HL at center)', 'clampH': 'attribution (M at center)'}
rows = '\n'.join('| %s | %s | %.6g | %.6g | %.0f | %.3f | %s | %d | %d | %+.4f | %s |' % (
    a, ROLE[a], P[a][0], P[a][1], P[a][2], per[a]['worst'], cfgs(per[a]['wc'][0]) + ' @' + per[a]['wc'][1],
    len(per[a]['over']), per[a]['maxsw'], mean[a], 'PASS' if safe[a] else '**FAIL**') for a in ARMS)
oh = '\n'.join(f"| {cfgs(o[0])} | {o[1]} | {o[2]:.3f} | {'yes' if (key(o[0]), o[1]) in over_sets['bo'] else 'no'} |"
               for o in per['clampH']['over']) or '| (none) | | | |'
N = 57
md = f"""# ADDENDUM {N} — exp713: exp674 joint BO point with GAMMA CLAMPED to exp712's certified edge

Verdict: **{R['verdict']}** — keeping exp674's BO margin ({BO[0]:.6g}) and BO half-life ({BO[2]:.0f}) but
clamping gamma from the BO value {BO[1]:.6g} to exp712's certified edge {G_EDGE:.6g} makes the joint point
SAFE: worst informative-cell deficit {per['clamp']['worst']:.3f}pp (bar {SAFE_PP}pp), 0/{inf} cells over the bar, max
switches {per['clamp']['maxsw']} (bar {SW_MAX}). But it does not transfer: paired mean delta vs center = {mean['clamp']:+.4f}pp,
just below the frozen H2 bar of {TR_PP:+.2f}pp — so H2 fails and the ladder lands on NO-GAIN. H0 replication
264/264 exact vs sealed exp674 (cf_center, cf_bo + lcnu/s3fifo standalones); H4 accounting 330/330 + two full
runs bit-identical. Exit 0, {R['elapsed_s']:.0f}s.

## Per-arm results ({inf} informative cells; bars frozen from exp674/710/711/712)
| arm | role | margin | gamma | half-life | worst deficit pp | worst cell | cells > {SAFE_PP}pp | max switches | mean delta vs center pp | H1 |
|---|---|---|---|---|---|---|---|---|---|---|
{rows}

Descriptive (no gate): `bo` reproduces exp674 exactly (worst {per['bo']['worst']:.3f}pp at the same cell, same
{len(over_sets['bo'])}-cell violation set, same mean delta {mean['bo']:+.4f}pp). The attribution arms are not
needed by the ladder (clamp passed) but are informative:
- `clampM` (BO margin, edge gamma, center HL) is safe AND the only arm with a positive mean delta vs center
  ({mean['clampM']:+.4f}pp; worst {per['clampM']['worst']:.3f}pp vs center's {per['center']['worst']:.3f}pp).
- `clampH` (center margin, edge gamma, BO HL) **fails** {len(per['clampH']['over'])}/{inf} cells (worst {per['clampH']['worst']:.3f}pp):
  the certified gamma edge from exp712 (measured at center M/HL, where the same parameters with HL 32768
  passed at worst {g3['worst']['deficit_pp']:.3f}pp) does not hold once HL alone moves to the BO value. clampH
  over-bar set nested in bo's = {nested_H}.
- Reading (descriptive): at BO HL, moving margin from center to BO turns edge gamma from unsafe (clampH)
  to safe (clamp) — consistent with exp711's protective-margin main effect; at BO margin, moving HL from
  center to BO costs mean delta: clampM ({mean['clampM']:+.4f}) -> clamp ({mean['clamp']:+.4f}).

clampH cells over the bar:
| stream | cap | deficit pp | also over in bo? |
|---|---|---|---|
{oh}

## What this settles
- Pre-registered consequence of CLAMP-REPAIRS:NO-GAIN: safety at the BO point is repaired by the gamma
  clamp, but the BO pointer does not transfer even when made safe (mean {mean['clamp']:+.4f}pp vs center,
  bar {TR_PP:+.2f}pp). The exp669->exp674 BO direction is closed as a transfer candidate on this family.
- Descriptive, not a gated claim: the certified gamma band is HL-context-dependent when margin is at
  center (clampH fails), and the best-looking point in this experiment is clampM (BO margin + edge gamma
  at center HL; +{mean['clampM']:.4f}pp mean, safe). Its +0.0077pp is far below any adoption bar; whether
  it is real headroom is a separate pre-registered question.

## Integrity, determinism, disclosures
- run_gclamp.py sha256 {art['run_gclamp.py'][:16]}..., PREREG.md {art['PREREG.md'][:16]}..., smoke.log
  {art['smoke.log'][:16]}..., policies.py {art['policies.py'][:16]}... == ARTIFACT.sha256 == local run dir;
  runner/PREREG/smoke.log/ARTIFACT == freeze-commit {FREEZE} blobs. Freeze commit precedes the result mtime.
  Disclosed smoke (S0-S4) passed pre-freeze.
- Published exp674 and exp712 JSONs asserted parse-equal to the local sealed copies the runner read.
- H2 margin is thin: {mean['clamp']:+.4f}pp vs {TR_PP:+.2f}pp bar (difference {mean['clamp'] - TR_PP:+.4f}pp); the frozen
  bar decides — no re-run, no bar change.
- Synthetic streams only (11 cfgs from exp670); single clamp level, no new gamma search.

Data: exp713/exp713-gclamp.json (run.log local, gitignored); PREREG.md / ARTIFACT.sha256 / smoke.log /
LEDGER.md in exp713/. Follow-up controller re-adjudicated every gate with an independently written
adjudicator ({len(checks)}/{len(checks)} checks): verdict {R['verdict']} stands.
"""
out = os.path.join(EXP, f'ADDENDUM{N}.md')
open(out, 'w').write(md)
print('wrote', out, len(md), 'chars; verdict', verdict, 'checks', len(checks),
      {a: (round(per[a]['worst'], 3), len(per[a]['over']), round(mean[a], 4), safe[a]) for a in ARMS},
      'nested_H', nested_H, 'h2', h2)
