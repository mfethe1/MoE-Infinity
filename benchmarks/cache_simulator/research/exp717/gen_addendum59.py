"""Independent adjudicator for exp717 -> ADDENDUM59.md. Recomputes every bar from raw cells."""
import hashlib, json, math, sys
from pathlib import Path

D = Path(__file__).resolve().parent
R = json.loads((D / "exp717-follow.json").read_text())
E = json.loads((Path.home() / "warp-work/exp715-moei-engineparity/exp715-engineparity.json").read_text())["traces"]
WS20 = {"granite": 1228, "hi": 3396, "lo": 4662}
TR = ("granite", "hi", "lo")
checks = []
ck = lambda n, c: checks.append((n, bool(c)))

ck("not smoke", R["smoke"] is False)
cells = {(c["tag"], c["cap"]): c for c in R["cells"]}
ck("27 cells", len(cells) == 27 and len(R["cells"]) == 27)
rows = []
for t in TR:
    N = E[t]["N"]
    for cs, e in E[t]["cells"].items():
        c = cells[(t, int(cs))]
        ck(f"{t}/{cs} N", c["N"] == N)
        ck(f"{t}/{cs} P0 lcnu", c["ghost_lcnu"] == e["lcnu"]["cpp"])
        ck(f"{t}/{cs} P0 s3", c["ghost_s3fifo"] == e["s3fifo"]["cpp"])
        ck(f"{t}/{cs} fb0", c["fallbacks"] == 0)
        best = max(v["cpp"] for v in e.values())
        rows.append({"t": t, "c": int(cs), "N": N, "best": best / N, "lcnu": e["lcnu"]["cpp"] / N,
                     "s3": e["s3fifo"]["cpp"] / N, "fo": c["follow"] / N, "cf": c["costfit"] / N,
                     "sw": c["switches"], "md": c["mean_D"], "ns": 1e9 * c["elapsed_s"] / N})
DIST = {"granite": 1262, "hi": 5097, "lo": 5842}
for t in TR:
    ck(f"ws {t}", R["ws"][t]["ws20"] == WS20[t] and R["ws"][t]["distinct"] == DIST[t])
for rr in R["rerun"]:
    base = cells[(rr["tag"], rr["cap"])]
    ck(f"rerun {rr['tag']}", all(rr[k] == base[k] for k in ("follow", "costfit", "ghost_lcnu", "ghost_s3fifo", "switches", "fallbacks")))
P0 = all(ok for _, ok in checks)
pp = lambda a, b: 100 * (a - b)
F1n = sum(pp(r["best"], r["fo"]) <= 0.5 for r in rows)
L1n = sum(pp(r["best"], r["lcnu"]) <= 0.5 for r in rows)
F2 = all(pp(r["fo"], r["lcnu"]) >= -0.25 for r in rows)
F3 = all(pp(r["fo"], r["cf"]) >= -0.5 for r in rows)
F1 = F1n >= 25
fol = "FOLLOW-SHIPPABLE" if (F1 and F2 and F3) else "FOLLOW-SAFE" if (F2 and F3) else "FOLLOW-REFUTED"

# static LOTO
norm = {"distinct": {t: R["ws"][t]["distinct"] for t in TR}, "ws20": {t: R["ws"][t]["ws20"] for t in TR}}
static = {}
for nm, n in norm.items():
    ratio = {}
    for t in TR:
        xs = sorted((r for r in rows if r["t"] == t), key=lambda r: r["c"])
        i = next(i for i, r in enumerate(xs) if r["s3"] > r["lcnu"])
        ratio[t] = math.sqrt(xs[i - 1]["c"] * xs[i]["c"]) / n[t]
    ok = 0; worst = 0; det = {}
    for h in TR:
        tr = [ratio[t] for t in TR if t != h]
        x = math.sqrt(tr[0] * tr[1])
        for r in (r for r in rows if r["t"] == h):
            pick = r["s3"] if r["c"] / n[h] >= x else r["lcnu"]
            g = pp(r["best"], pick); ok += g <= 0.5; worst = max(worst, g)
        det[h] = round(x, 3)
    static[nm] = {"ratios": {t: round(v, 3) for t, v in ratio.items()}, "thresholds": det, "within": ok,
                  "worst_pp": worst, "pass": ok >= 25}
verdict = "INVALID" if not P0 else fol + "|" + "|".join(f"STATIC-{k}:{'PASS' if v['pass'] else 'FAIL'}" for k, v in static.items())
bad = [n for n, ok in checks if not ok]
print("checks", len(checks), "bad", bad[:5]); print("VERDICT", verdict, "F1", F1n, "L1", L1n, "F2", F2, "F3", F3)
for r in rows:
    print(r["t"], r["c"], f"gapFO {pp(r['best'], r['fo']):+.3f} gapL {pp(r['best'], r['lcnu']):+.3f} FO-L {pp(r['fo'], r['lcnu']):+.3f} FO-CF {pp(r['fo'], r['cf']):+.3f} sw {r['sw']} D {r['md']:.1f} {r['ns']:.0f}ns")
print(json.dumps(static, indent=0))
if "--write" not in sys.argv:
    sys.exit(0)
assert P0, bad
fo_cf = sorted(pp(r["fo"], r["cf"]) for r in rows)
med = fo_cf[13]
h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
tl = lambda r: f"{r['t']}@{r['c']}"
wF = max(rows, key=lambda r: pp(r["best"], r["fo"]))
wR = min(rows, key=lambda r: pp(r["fo"], r["lcnu"]))
gain = max(rows, key=lambda r: pp(r["fo"], r["lcnu"]))
md = f"""# ADDENDUM59 — exp717: a realizable LCNU/S3-FIFO arbiter (FOLLOW) on 3 full real decode traces

**Verdict (PREREG frozen at c738bed): `{verdict}`**

exp715 showed the shipped LCNU default within 0.5pp of the best of 13 policies in only 17/27 cells; S3-FIFO wins the
upper capacity tail. FOLLOW keeps ONE real set of C expert slots, runs the sealed CostFit control law over metadata-only
LCNU and S3-FIFO ghosts, and on a miss evicts a resident expert the current leader ghost does not hold (lazy, demand-only migration).

## Bars
- **P0 validity: PASS.** Ghost LCNU / S3-FIFO hits == exp715 C++ hits 27/27 each; 0 fallbacks; D-invariant asserted every 65536 accesses;
  distinct/WS20 recomputed == sealed; 3 reruns bit-identical.
- **F1 within 0.5pp of best-of-13: {F1n}/27 ({'PASS' if F1 else 'FAIL'}; LCNU default 17/27).** Worst FOLLOW gap {pp(wF['best'], wF['fo']):.3f}pp at {tl(wF)}.
  FOLLOW *exceeds* the best single shipped policy in {sum(pp(r['fo'], r['best']) > 0 for r in rows)}/27 cells (max {max(pp(r['fo'], r['best']) for r in rows):+.3f}pp at {tl(max(rows, key=lambda r: pp(r['fo'], r['best'])))}):
  the lazily migrated set is a hybrid of the two ghosts, not a copy of either. This is descriptive, not a pre-registered bar.
- **F2 never worse than LCNU by >0.25pp: {'PASS' if F2 else 'FAIL'}.** Worst FOLLOW-LCNU {pp(wR['fo'], wR['lcnu']):+.3f}pp at {tl(wR)}; best {pp(gain['fo'], gain['lcnu']):+.3f}pp at {tl(gain)}.
- **F3 realizability cost vs optimistic CostFit >= -0.5pp: {'PASS' if F3 else 'FAIL'}.** FOLLOW-CostFit min {fo_cf[0]:+.3f} / median {med:+.3f} / max {fo_cf[-1]:+.3f}pp.
- **Static leave-one-trace-out rules:**
""" + "\n".join(f"  - {k}: crossover ratios {v['ratios']}, held-out thresholds {v['thresholds']}, within 0.5pp {v['within']}/27, worst {v['worst_pp']:.2f}pp -> {'PASS' if v['pass'] else 'FAIL'}" for k, v in static.items()) + f"""

## Per cell (pp; best = best of 13 shipped policies, exp715)
| trace@cap | best-FOLLOW | best-LCNU | FOLLOW-LCNU | FOLLOW-CostFit | switches | mean lag |D| |
|---|---|---|---|---|---|---|
""" + "\n".join(f"| {tl(r)} | {pp(r['best'], r['fo']):.3f} | {pp(r['best'], r['lcnu']):.3f} | {pp(r['fo'], r['lcnu']):+.3f} | {pp(r['fo'], r['cf']):+.3f} | {r['sw']} | {r['md']:.1f} |" for r in rows) + f"""

## Independent cross-check
xcheck_brute.py re-implements the real-set bookkeeping by brute force: it recomputes R minus the leader every step and orders victims by explicit timestamps.
It matched FOLLOW's hits and switches on 6 runs (xcheck.log), 3 of them full streams.
The first version mismatched granite@1024 by 6 hits. The cause was the brute's same-step tie order, not FOLLOW: two keys left the leader in the same step and were ordered differently.
Tie-breaking was fixed to the ghost eviction order, and all 6 runs then match.

## Scope
Simulation of the decode stream only. Python wall time per access is not an engine cost; in C++ FOLLOW costs two policy updates plus O(1) set ops per access.
Ghost metadata is keys only (no expert weights). Real-engine measurement: exp716 on Winnie.

## Provenance
- result exp717-follow.json sha256 {h(D / 'exp717-follow.json')}; frozen ARTIFACT.sha256 (== c738bed):
```
{(D / 'ARTIFACT.sha256').read_text().strip()}
```
- gen_addendum59.py recomputes all bars from raw cells; {len(checks)} checks PASS; runner wall {R['total_elapsed_s']:.0f}s.
"""
out = D / "ADDENDUM59.md"
assert not out.exists() or "--force" in sys.argv
out.write_text(md); print("WROTE", out)
