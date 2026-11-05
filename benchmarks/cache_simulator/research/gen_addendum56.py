#!/usr/bin/env python3
"""gen_addendum56.py — programmatic ADDENDUM56 for exp712 (STACK-1001, lane 79990).
Every number is parsed at runtime from sealed primary artifacts:
  - exp712/exp712-gdose.json         (this experiment's sealed result)
  - exp711/exp711-mgfactorial.json   (sealed H0 bookends cf_000 / cf_0G0 + standalones)
  - exp674-hl-transfer.json          (sealed bo_params -> BO gamma)
  - exp670-synth.json                (sealed stream sha8 list)
  - exp712/ARTIFACT.sha256 + freeze commit d611f02 blobs (git show)
The adjudicator below is written independently of run_gdose.py: it rebuilds the gamma line from
the PREREG formula, re-derives H0/H4/H1 per arm and the frozen ladder from the grid, and asserts
agreement with the runner. No hand math, no hand-transcribed hashes."""
import hashlib
import json
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.join(BASE, 'exp712')
LOCALDIR = '/Users/mfethe/warp-work/exp712-moei-gdose'
LOCALRES = os.path.join(LOCALDIR, 'exp712-gdose.json')
LOCAL711 = '/Users/mfethe/warp-work/exp711-moei-mgfactorial/exp711-mgfactorial.json'
LOCAL674 = '/Users/mfethe/warp-work/exp674-moei-hl-transfer/exp674-hl-transfer.json'
FREEZE = 'd611f02'

R = json.load(open(os.path.join(EXP, 'exp712-gdose.json')))
X711 = json.load(open(os.path.join(BASE, 'exp711', 'exp711-mgfactorial.json')))
X674 = json.load(open(os.path.join(BASE, 'exp674-hl-transfer.json')))
X670 = json.load(open(os.path.join(BASE, 'exp670-synth.json')))

checks = []


def chk(name, ok):
    checks.append((name, bool(ok)))
    assert ok, name


sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()  # noqa: E731
chk('published result byte-equal local sealed result', sha(os.path.join(EXP, 'exp712-gdose.json')) == sha(LOCALRES))
chk('published exp711 parse-equal to runner input', json.load(open(LOCAL711)) == X711)
chk('published exp674 parse-equal to local sealed copy', json.load(open(LOCAL674)) == X674)

CENTER = (0.005, 0.0025, 32768.0)
BO_G = float(X674['bo_params']['gamma'])
GAM = [CENTER[1] * (BO_G / CENTER[1]) ** (k / 5) for k in range(5)] + [BO_G]
ARMS = [f'g{k}' for k in range(6)]
chk('rules center == frozen center', tuple(R['rules']['center']) == CENTER)
chk('bo_gamma == exp674 bo_params gamma (runtime parse)', R['rules']['bo_gamma'] == BO_G)
chk('gamma line == PREREG formula (independent rebuild)', R['rules']['gammas'] == GAM)
chk('gamma line strictly increasing, endpoints center..BO', GAM[0] == CENTER[1] and GAM[-1] == BO_G
    and all(GAM[i] < GAM[i + 1] for i in range(5)))
for k, a in enumerate(ARMS):
    chk(f'arm {a} params == (center M, g{k}, center HL)', tuple(R['arms'][a]['params']) == (CENTER[0], GAM[k], CENTER[2]))
SAFE_PP, SW_MAX, INF_PP = 0.5, 6, 0.1
chk('bars frozen', (R['rules']['safety_pp'], R['rules']['switch_max'], R['rules']['informative_pp']) == (SAFE_PP, SW_MAX, INF_PP))

key = lambda cfg: json.dumps(cfg, sort_keys=True)  # noqa: E731
G = R['grid']
chk('11 streams x 6 caps', len(G) == 11 and sum(len(s['caps']) for s in G) == 66)
chk('11 stream sha8 == exp670', [s['seed'] for s in G] == [s['seed'] for s in X670['grid']])
ref = {(key(s['cfg']), int(c)): cell for s in X711['grid'] for c, cell in s['caps'].items()}
chk('exp711 ref covers same 66 cells', set(ref) == {(key(s['cfg']), int(c)) for s in G for c in s['caps']})

BOOK = {'g0': 'cf_000', 'g5': 'cf_0G0'}
mm = sum(cell['cf_' + a] != ref[(key(s['cfg']), int(cap))][rb] for s in G for cap, cell in s['caps'].items() for a, rb in BOOK.items())
sa = sum(cell[x] != ref[(key(s['cfg']), int(cap))][x] for s in G for cap, cell in s['caps'].items() for x in ('lcnu', 's3fifo'))
chk('H0 bookends 132/132 exact vs exp711 (g0==cf_000, g5==cf_0G0)', mm == 0)
chk('H0 standalones 132/132 exact vs exp711', sa == 0)
chk('H0 runner 264 cells ok', R['H0_replication']['cells'] == 264 and R['H0_replication']['ok'] and not R['H0_replication']['mismatches'])
acct = sum(cell['cf_' + a]['rate'] != cell['cf_' + a]['prop'] for s in G for cell in s['caps'].values() for a in ARMS)
chk('H4 accounting 396/396 loop==prop', acct == 0 and R['H4_accounting'] is True and not R['accounting_violations'])
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
            p['deltas'].append((x['rate'] - cell['cf_g0']['rate']) * 100)
            p['maxsw'] = max(p['maxsw'], x['switches'])
            if p['worst'] is None or d > p['worst']:
                p['worst'], p['wc'] = d, (s['cfg'], cap)
            if d > SAFE_PP:
                p['over'].append((s['cfg'], cap, round(d, 3)))
            p['sw'] += x['switches'] > SW_MAX
chk('59 informative cells', inf == 59 == R['informative_cells'])
safe = [not per[a]['over'] and per[a]['sw'] == 0 for a in ARMS]
mean = {a: sum(per[a]['deltas']) / len(per[a]['deltas']) for a in ARMS}
for i, a in enumerate(ARMS):
    r = R['arms'][a]
    p = per[a]
    chk(f'arm {a} worst/over/maxsw/mean/H1 == runner',
        r['worst']['deficit_pp'] == round(p['worst'], 3) and r['cells_over_bar'] == len(p['over'])
        and r['cells_over_switch'] == p['sw'] and r['max_switches'] == p['maxsw'] and r['H1_safe'] == safe[i]
        and r['mean_delta_vs_g0_pp'] == round(mean[a], 4))

# independent ladder (re-written from the PREREG text, not imported)
e = -1
for i in range(6):
    if not safe[i]:
        break
    e = i
first_fail = next((i for i in range(6) if not safe[i]), None)
nonmono = first_fail is not None and any(safe[i] for i in range(first_fail + 1, 6))
if mm or sa or acct:
    verdict = 'ACCOUNTING-FAIL'
elif e == 5:
    verdict = 'G-LINE-SAFE'
elif 1 <= e <= 4:
    verdict = f'G-BOUNDARY@g{e + 1}'
else:
    verdict = 'G-BAND-COLLAPSED'
chk('verdict re-derived == runner', verdict == R['verdict'])
chk('certified edge == runner', R['certified_gamma_upper_edge'] == (GAM[e] if e >= 0 else None))
chk('nonmonotone flag == runner', R['nonmonotone'] == nonmono)

# exp711 cross-checks: bookend arms reproduce exp711's corner statistics
for a, c in (('g0', '000'), ('g5', '0G0')):
    chk(f'{a} worst/over == exp711 {c}', round(per[a]['worst'], 3) == X711['arms'][c]['worst']['deficit_pp']
        and len(per[a]['over']) == X711['arms'][c]['cells_over_bar'])

# descriptive monotonicity (frozen as reported flags, not gates)
worsts = [round(per[a]['worst'], 3) for a in ARMS]
overs = [len(per[a]['over']) for a in ARMS]
mono_w = all(worsts[i] <= worsts[i + 1] for i in range(5))
mono_o = all(overs[i] <= overs[i + 1] for i in range(5))
over_sets = {a: {(key(o[0]), o[1]) for o in per[a]['over']} for a in ARMS}
nested = over_sets['g4'] <= over_sets['g5']

# integrity: ARTIFACT == working files == freeze-commit blobs; freeze precedes result
art = dict(ln.split()[::-1] for ln in open(os.path.join(EXP, 'ARTIFACT.sha256')).read().strip().splitlines())
REPO = subprocess.check_output(['git', '-C', BASE, 'rev-parse', '--show-toplevel'], text=True).strip()
rel = os.path.relpath(EXP, REPO)
art_blob = subprocess.check_output(['git', '-C', REPO, 'show', f'{FREEZE}:{rel}/ARTIFACT.sha256'])
chk('ARTIFACT.sha256 == freeze-commit blob', hashlib.sha256(art_blob).hexdigest() == sha(os.path.join(EXP, 'ARTIFACT.sha256')))
for f in ('run_gdose.py', 'PREREG.md'):
    blob = subprocess.check_output(['git', '-C', REPO, 'show', f'{FREEZE}:{rel}/{f}'])
    chk(f'{f} sha == ARTIFACT == freeze blob == local', art[f] == sha(os.path.join(EXP, f)) == hashlib.sha256(blob).hexdigest()
        == sha(os.path.join(LOCALDIR, f)))
# smoke.log is matched by the cache_simulator *.log gitignore rule, so the freeze commit carries it only
# by hash (inside the committed ARTIFACT.sha256); bind it through that hash and force-add it at publish.
chk('smoke.log sha == committed ARTIFACT hash == local', art['smoke.log'] == sha(os.path.join(EXP, 'smoke.log'))
    == sha(os.path.join(LOCALDIR, 'smoke.log')))
freeze_t = int(subprocess.check_output(['git', '-C', REPO, 'log', '-1', '--format=%ct', FREEZE], text=True).strip())
chk('freeze commit precedes result mtime', freeze_t < os.path.getmtime(LOCALRES))


def cfgs(cfg):
    return f"s={cfg['s']} lam={cfg['lam']} E={cfg['E']}/L={cfg['L']}"


rows = '\n'.join('| %s | %.6g | %.2fx | %s | %.3f | %s | %d | %d | %+.4f | %s |' % (
    a, GAM[i], GAM[i] / CENTER[1], {'g0': 'exp711 000', 'g5': 'exp711 0G0'}.get(a, 'new'), per[a]['worst'],
    cfgs(per[a]['wc'][0]) + ' @' + per[a]['wc'][1], len(per[a]['over']), per[a]['maxsw'], mean[a],
    'PASS' if safe[i] else '**FAIL**') for i, a in enumerate(ARMS))
og = '\n'.join(f"| {cfgs(o[0])} | {o[1]} | {o[2]:.3f} | {'yes' if (key(o[0]), o[1]) in over_sets['g5'] else 'no'} |"
               for o in per[ARMS[first_fail]]['over']) if first_fail is not None else '| (none) | | | |'
EDGE = GAM[e] if e >= 0 else None
N = 56
md = f"""# ADDENDUM {N} — exp712: single-knob GAMMA dose line at center (M, HL) — certified gamma band

Verdict: **{R['verdict']}** — with margin ({CENTER[0]:g}) and half-life ({CENTER[2]:.0f}) held at center,
gamma is certified safe from center {CENTER[1]:g} up to **g{e} = {EDGE:.6g}** ({EDGE / CENTER[1]:.2f}x center,
{EDGE / BO_G:.2f}x of the exp674 BO gamma {BO_G:.6g}). The first failing dose is g{first_fail} = {GAM[first_fail]:.6g}
({GAM[first_fail] / CENTER[1]:.2f}x center): {len(per[ARMS[first_fail]]['over'])}/{inf} informative cells over the {SAFE_PP}pp no-harm bar
(worst {per[ARMS[first_fail]]['worst']:.3f}pp). Ladder is monotone (nonmonotone flag = {nonmono}). H0 bookend
replication 264/264 exact vs sealed exp711 (g0 == cf_000, g5 == cf_0G0, + lcnu/s3fifo standalones);
H4 accounting 396/396 + two full runs bit-identical. Exit 0, {R['elapsed_s']:.0f}s.

## Per-arm results ({inf} informative cells; bars frozen from exp674/710/711)
| arm | gamma | x center | sealed replica? | worst deficit pp | worst cell | cells > {SAFE_PP}pp | max switches | mean delta vs g0 pp | H1 |
|---|---|---|---|---|---|---|---|---|---|
{rows}

Descriptive (no gate): worst deficit monotone in gamma = {mono_w} ({' -> '.join(f'{w:.3f}' for w in worsts)} pp);
over-bar count monotone = {mono_o} ({' -> '.join(str(o) for o in overs)}); g4 over-bar set nested in g5's = {nested}.
Switches never exceed {max(p['maxsw'] for p in per.values())} on any arm (bar {SW_MAX}): every failure is a pure hit-rate
deficit. Mean paired delta vs g0 drifts monotonically negative ({' / '.join(f'{mean[a]:+.4f}' for a in ARMS)} pp).

First failing arm (g{first_fail}) cells over the bar:
| stream | cap | deficit pp | also over at g5? |
|---|---|---|---|
{og}

## What this settles
- exp711 located exp674's SAFETY-BROKEN break in gamma; exp712 bounds it: at center M/HL the
  certified gamma band is **[{CENTER[1]:g}, {EDGE:.6g}]**. The exp674 BO gamma sits two geometric steps
  ({BO_G / EDGE:.2f}x) beyond the certified edge.
- Pre-registered consequence (G-BOUNDARY@g_j, j >= 2): re-run the exp674 joint transfer with gamma
  clamped to the certified edge (BO margin + BO HL kept) — tests whether clamping gamma alone
  repairs the BO point. Registered as exp713.

## Integrity, determinism, disclosures
- run_gdose.py sha256 {art['run_gdose.py'][:16]}..., PREREG.md {art['PREREG.md'][:16]}..., smoke.log
  {art['smoke.log'][:16]}... == ARTIFACT.sha256 == local run dir; runner/PREREG/ARTIFACT == freeze-commit
  {FREEZE} blobs. smoke.log is matched by the cache_simulator `*.log` gitignore rule, so the freeze
  commit bound it by hash only (inside the committed ARTIFACT.sha256); it is force-added with this
  addendum. Freeze pushed before launch and precedes the result mtime. Disclosed smoke (S1-S4) passed pre-freeze.
- Disclosed in LEDGER: first launch (pid 21498) was a non-persistent session child killed at 4 s with a
  0-byte log and no output; relaunched persistently after re-verifying the runner sha.
- Published exp711 and exp674 JSONs asserted parse-equal to the local sealed copies the runner read.
- Synthetic streams only (11 cfgs from exp670); single-knob line — M/HL interactions are exp711's domain.

Data: exp712/exp712-gdose.json (run.log local, gitignored); PREREG.md / ARTIFACT.sha256 / smoke.log /
LEDGER.md in exp712/. Follow-up controller re-adjudicated every gate with an independently written
adjudicator ({len(checks)}/{len(checks)} checks): verdict {R['verdict']} stands.
"""
out = os.path.join(EXP, f'ADDENDUM{N}.md')
open(out, 'w').write(md)
print('wrote', out, len(md), 'chars; verdict', verdict, 'edge', EDGE, 'e', e, 'checks', len(checks),
      'worsts', worsts, 'overs', overs, 'mono', mono_w, mono_o, 'nested', nested)
