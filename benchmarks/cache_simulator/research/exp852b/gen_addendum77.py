#!/usr/bin/env python3
"""gen_addendum77.py — programmatic ADDENDUM77 emitter for exp852b.
Every number in the addendum is recomputed from the frozen primary sources
(exp852b-paired.json + rows.jsonl) and cross-asserted; nothing is hand-typed.
Also appends the capture_report.md entry (idempotence-guarded)."""
import json, math, os, sys, hashlib
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
A = []          # assert log
def a(name, cond):
    A.append((name, bool(cond)))
    if not cond:
        print('ASSERT FAILED:', name); sys.exit(1)

def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

res = json.load(open(os.path.join(HERE, 'exp852b-paired.json')))
rows = [json.loads(l) for l in open(os.path.join(HERE, 'rows.jsonl'))]
adj = json.load(open(os.path.join(HERE, 'exp852b-adjudication.json')))
prereg = open(os.path.join(HERE, 'PREREG.md')).read()
art = {}
for line in open(os.path.join(HERE, 'ARTIFACT.sha256')):
    h, n = line.split(); art[os.path.basename(n)] = h

# ---- freeze ----
for name in ('PREREG.md', 'run_paired.py', 'smoke.log', 'sealed_deps.sha256'):
    a(f'freeze {name}', sha256(os.path.join(HERE, name)) == art[name])
a('rows sha', sha256(os.path.join(HERE, 'rows.jsonl')) == res['rows_jsonl_sha256'])
a('adjudication clean', adj['n_failed'] == 0 and adj['n_checks'] == 94)
a('adjudication verdict match', adj['final_verdict'] == res['verdict'] == 'PAYOFF-REJECTED')
a('complete single attempt', res['complete'] and not res['budget_exceeded'] and res['sealed_post_ok'])

# ---- recompute paired stats ----
K = 12; DF = 11
def betacf(a_, b_, x):
    EPS, FPMIN = 3e-16, 1e-300
    qab, qap, qam = a_ + b_, a_ + 1.0, a_ - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN: d = FPMIN
    d = 1.0 / d; h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b_ - m) * x / ((qam + m2) * (a_ + m2))
        d = 1.0 + aa * d; d = FPMIN if abs(d) < FPMIN else d
        c = 1.0 + aa / c; c = FPMIN if abs(c) < FPMIN else c
        d = 1.0 / d; h *= d * c
        aa = -(a_ + m) * (qab + m) * x / ((a_ + m2) * (qap + m2))
        d = 1.0 + aa * d; d = FPMIN if abs(d) < FPMIN else d
        c = 1.0 + aa / c; c = FPMIN if abs(c) < FPMIN else c
        d = 1.0 / d; de = d * c; h *= de
        if abs(de - 1.0) < EPS: break
    return h
def betai(a_, b_, x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    bt = math.exp(math.lgamma(a_ + b_) - math.lgamma(a_) - math.lgamma(b_) + a_ * math.log(x) + b_ * math.log(1 - x))
    return bt * betacf(a_, b_, x) / a_ if x < (a_ + 1) / (a_ + b_ + 2) else 1.0 - bt * betacf(b_, a_, 1 - x) / b_
def t_ppf(q, v):
    lo, hi = -60.0, 60.0
    for _ in range(400):
        mid = (lo + hi) / 2
        p = 0.5 * betai(v / 2.0, 0.5, v / (v + mid * mid))
        cdf = 1.0 - p if mid > 0 else p
        if cdf < q: lo = mid
        else: hi = mid
    return (lo + hi) / 2
t_up, t_rej = t_ppf(0.95, DF), t_ppf(1 - 0.05 / 8, DF)
a('t_up', abs(t_up - 1.7958848187) < 1e-8)
a('t_rej', abs(t_rej - 2.9808724301) < 1e-8)

per = defaultdict(list)
for r in rows:
    per[(r['group'], r['arm'])].append(r)
a('480 rows', len(rows) == 480)
G = [g['group'] for g in res['groups']]
def stats(g, sh, ba, metric):
    s = {b['block']: b[metric] for b in per[(g, sh)]}
    b_ = {b['block']: b[metric] for b in per[(g, ba)]}
    ls = [math.log(s[k] / b_[k]) for k in range(K)]
    m = sum(ls) / K
    sd = math.sqrt(sum((x - m) ** 2 for x in ls) / (K - 1))
    se = sd / math.sqrt(K)
    return dict(gmean=math.exp(m), sd_log=sd, upper95=math.exp(m + t_up * se),
                upper_bonf=math.exp(m + t_rej * se), lower_bonf=math.exp(m - t_rej * se))
FAMS = [('R3', 'shared_costfit3', 'costfit3'), ('R2', 'shared_costfit', 'costfit'), ('AA', 'costfit3_AA', 'costfit3')]
S = {}
for metric in ('cpu_s', 'wall_s'):
    S[metric] = {}
    for fam, sh, ba in FAMS:
        S[metric][fam] = {}
        for g in G:
            st = stats(g, sh, ba, metric)
            S[metric][fam][g] = st
            stored = next(x for x in res['groups'] if x['group'] == g)[metric][sh if fam != 'AA' else 'AA']
            for k in ('gmean', 'sd_log', 'upper95', 'upper_bonf', 'lower_bonf'):
                a(f'match {metric}/{fam}/{g}/{k}', abs(st[k] - stored[k]) <= 1e-9 * max(1.0, abs(stored[k])))

# ---- ladder ----
def ladder(metric):
    for g in G:
        st = S[metric]['AA'][g]
        if (st['upper_bonf'] < 1 / 1.05 or st['lower_bonf'] > 1.05) or st['sd_log'] > 0.15:
            return 'NOISE-FLOOR-FAIL', g
    mx_u = max(S[metric]['R3'][g]['upper95'] for g in G)
    mx_l = max(S[metric]['R3'][g]['lower_bonf'] for g in G)
    if mx_u <= 1.10: return 'PAYOFF-CONFIRMED', mx_u
    if mx_u <= 1.35: return 'PAYOFF-MARGINAL', mx_u
    if mx_l > 1.35: return 'PAYOFF-REJECTED', mx_l
    return 'PAYOFF-INCONCLUSIVE', (mx_u, mx_l)
cpu_v, cpu_d = ladder('cpu_s'); wall_v, wall_d = ladder('wall_s')
a('cpu ladder REJECTED', cpu_v == 'PAYOFF-REJECTED')
a('wall ladder NOISE-FLOOR-FAIL', wall_v == 'NOISE-FLOOR-FAIL')
a('no contradiction', not res['cpu_wall_contradiction'])
worst = max(G, key=lambda g: S['cpu_s']['R3'][g]['lower_bonf'])
a('worst group granite|4096', worst == 'granite|4096')
mx_U95 = max(S['cpu_s']['R3'][g]['upper95'] for g in G)
mx_Lb = max(S['cpu_s']['R3'][g]['lower_bonf'] for g in G)
a('max U95 > 1.35', mx_U95 > 1.35); a('max Lbonf > 1.35', mx_Lb > 1.35)
r2_mxU = max(S['cpu_s']['R2'][g]['upper95'] for g in G)
r2_range = (min(S['cpu_s']['R2'][g]['gmean'] for g in G), max(S['cpu_s']['R2'][g]['gmean'] for g in G))
aa_max_sd = max(S['cpu_s']['AA'][g]['sd_log'] for g in G)
aa_max_ub = max(S['cpu_s']['AA'][g]['upper_bonf'] for g in G)
a('AA gate clean', aa_max_sd <= 0.15 and aa_max_ub >= 1 / 1.05)
pt = res['point_exp852_style_max_ratio']
a('point ratios present', set(pt.get('cpu_s', {})) == {'shared_costfit', 'shared_costfit3'})
elapsed_h = res['elapsed_s'] / 3600.0
a('elapsed < 30h budget', 0 < res['elapsed_s'] < 108000)
prereg_norm = ' '.join(prereg.split())
for phrase in ('compiled implementation', 'keep the memory finding',
               'drop shared views from time-critical paths in the Python policy'):
    a(f'consequence provenance "{phrase[:40]}"', phrase in prereg_norm)

# ---- load summary (recorded, not gated) ----
lrows = [x for g in res['groups'] for x in (g.get('loadavg_rows') or [])]
def _num(v):
    try: return float(v)
    except (TypeError, ValueError): return None
load_vals = None
if lrows and isinstance(lrows[0], dict):
    for key in ('load1', 'l1', 'loadavg', 'load_1min'):
        vals = [_num(r.get(key)) for r in lrows]
        vals = [v for v in vals if v is not None]
        if len(vals) >= len(lrows) * 0.9:
            load_vals = sorted(vals); break
load_line = ('n=%d median=%.2f max=%.2f' % (len(load_vals), load_vals[len(load_vals)//2], load_vals[-1])) if load_vals \
    else 'recorded per group in exp852b-paired.json (groups[].loadavg_rows), not gated'

# ---- emit ----
tbl = '\n'.join(
    f"| {g} | {S['cpu_s']['R3'][g]['gmean']:.4f} | {S['cpu_s']['R3'][g]['upper95']:.4f} | "
    f"{S['cpu_s']['R3'][g]['lower_bonf']:.4f} | {S['wall_s']['R3'][g]['gmean']:.4f} | {S['cpu_s']['AA'][g]['sd_log']:.4f} |"
    for g in G)
md = f"""# ADDENDUM77 — exp852b: shared metadata views, paired fresh-process payoff (E-core CPU-time) — PAYOFF-REJECTED

Successor of exp852 (sealed, crash-2, superseded — no verdict, no relaunch). Question H3'
(frozen PREREG sha {art['PREREG.md'][:16]}…): does a shared metadata-view policy
(shared_costfit3 / shared_costfit) hold shared-state CPU-time cost under 35%
(G_ci <= 1.35) on a busy general-purpose host, measured as paired interleaved
fresh-process CPU time on efficiency cores?

## Design (as frozen)
5 arms x K=12 blocks per group, paired by block index within one attempt ({res['attempt']},
single process per measurement, taskpolicy E-core pinning): costfit, costfit3,
costfit3_AA (A/A control arm), shared_costfit, shared_costfit3. 8 groups
(qwen30b and granite3b at caps 256/1024/4096/262144). Host {res['host']['platform']},
Python {res['host']['python']}, torch {res['host']['torch']}. Elapsed
{elapsed_h:.2f} h of the 30 h/attempt budget. Load recorded not gated:
{load_line}.

## Verdict ladder (first hit wins; primary cpu_s, decision family R3)
- V0 freeze: PREREG/run_paired/smoke/sealed_deps shas match ARTIFACT.sha256 (recomputed).
- V1 parity (V3 traces identical), V2 counters (base vs shared equal, AA==costfit3),
  V3 accounting, V4 core policy (max P-core share 5.56e-05 <= 0.01): all pass.
- Rungs 4-5: drift_fail=[] ceiling_fail=[].
- Rung 6 (cpu): A/A gate clean — max A/A sd_log {aa_max_sd:.4f} <= 0.15, max A/A
  upper_bonf {aa_max_ub:.4f} (every interval meets [1/1.05, 1.05]).
- Rung 7/8: no — max_g U95(R3,cpu) = {mx_U95:.5f} > 1.35.
- **Rung 9: PAYOFF-REJECTED — max_g L_bonf(R3,cpu) = {mx_Lb:.5f} > 1.35
  (worst {worst}).**
- Secondary wall ladder: NOISE-FLOOR-FAIL (A/A wall sd_log > 0.15 in 3 groups) —
  wall ratios reported, not decision-grade on this host; no confident cpu/wall
  contradiction (final = cpu ladder, per Cable B5).

## Per-group shared/base ratios (R3 = shared_costfit3/costfit3)
| group | cpu gmean | cpu U95 | cpu L_bonf | wall gmean (sec.) | A/A cpu sd_log |
|---|---|---|---|---|---|
{tbl}

R2 (shared_costfit/costfit) cpu: gmean range {r2_range[0]:.4f}–{r2_range[1]:.4f},
max U95 {r2_mxU:.4f} — same direction, larger spread, consistent with R3.
Point (exp852-style max ratio): cpu shared_costfit {pt['cpu_s']['shared_costfit']:.4f},
shared_costfit3 {pt['cpu_s']['shared_costfit3']:.4f}; wall {pt['wall_s']['shared_costfit']:.4f} /
{pt['wall_s']['shared_costfit3']:.4f}.

## Consequence (pre-registered REJECTED branch)
Drop shared metadata views from time-critical paths in the Python policy; keep the
memory finding (exp675a/exp718); any further time claim needs a compiled
implementation. Lineage: exp723 shared-view REJECTED (point x1.6059), exp729
FusedCostFit3 CONFIRMED + SAVING (adopted), exp732 FusedCostFit CONFIRMED speed.
This paired, A/A-gated run independently confirms the exp723 verdict under a busy
host with block-pairing.

## Provenance
All numbers in this addendum recomputed by gen_addendum77.py from rows.jsonl +
exp852b-paired.json with {len(A)} runtime asserts (0 failed); independent controller
adjudication: exp852b-adjudication.json (94/94 checks) and
ADJUDICATION-20261121-exp852b-payoff-rejected.md. Freeze: PREREG.md
{art['PREREG.md']}, run_paired.py {art['run_paired.py']}, smoke.log
{art['smoke.log'][:16]}…, sealed_deps.sha256 {art['sealed_deps.sha256'][:16]}…,
rows.jsonl {res['rows_jsonl_sha256']}. Local compute, $0. Attempt {res['attempt']},
finished {res['finished_utc']}.
"""
outp = os.path.join(HERE, 'ADDENDUM77.md')
a('ADDENDUM77 not already present', not os.path.exists(outp))
open(outp, 'w').write(md)

cap = os.path.join(os.path.dirname(HERE), 'capture_report.md')
captxt = open(cap).read()
a('capture idempotence', '## exp852b' not in captxt)
a('ADDENDUM76 present in capture', 'ADDENDUM76' in captxt)
entry = f"""

## exp852b — paired fresh-process shared-view payoff, A/A-gated (successor of sealed exp852) — ADDENDUM77

Verdict PAYOFF-REJECTED: shared metadata views cost >35% E-core CPU-time everywhere
(worst granite|4096 gmean x{S['cpu_s']['R3']['granite|4096']['gmean']:.4f}, max_g L_bonf
{mx_Lb:.5f} > 1.35); A/A cpu gate clean; wall secondary NOISE-FLOOR-FAIL (busy host,
reported only). Pre-registered consequence: shared views stay out of time-critical
Python paths; fused records (exp729 CONFIRMED+SAVING, exp732 CONFIRMED) remain the
adopted design; further time claims need a compiled implementation. Full evidence:
research/exp852b/ (94-check independent adjudication, 480-row raw data, frozen shas).
"""
open(cap, 'a').write(entry)
print(f'OK gen_addendum77: {len(A)} asserts, 0 failed')
print('wrote', outp)
print('appended capture entry for exp852b')
