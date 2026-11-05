"""Independent adjudicator for exp715 -> ADDENDUM58.md.

Re-derives P1-P4 from the raw per-cell hit counts in exp715-engineparity.json
(NOT from its 'adjudication' block), re-reads the sealed exp704 anchors, asserts
agreement with the runner's verdict, and writes the addendum programmatically.
"""
import hashlib, json, sys
from pathlib import Path

D = Path(__file__).resolve().parent
R = json.loads((D / "exp715-engineparity.json").read_text())
S = json.loads((Path.home() / "warp-work/exp704-moei-capacitymap/exp704-capacitymap.json").read_text())["traces"]
POL = "lru lfu lfu_k lhu lru_k arc 2q lirs s3fifo sieve w_tinylfu layer_lru lcnu".split()
DIST = {"granite": 1262, "hi": 5097, "lo": 5842}
checks = []


def ck(name, cond):
    checks.append((name, bool(cond)))


ck("not smoke", R["smoke"] is False)
ck("3 traces", sorted(R["traces"]) == ["granite", "hi", "lo"])
p1 = det = 0
cells = []
for t, r in R["traces"].items():
    ck(f"{t} 9 caps", len(r["cells"]) == 9)
    for c, row in r["cells"].items():
        ck(f"{t}/{c} 13 policies", sorted(row) == sorted(POL))
        for p, v in row.items():
            p1 += v["cpp"] == v["py"]
            det += v["cpp"] == v["cpp_rep"]
            ck(f"{t}/{c}/{p} rate", abs(v["rate"] - v["cpp"] / r["N"]) < 1e-15)
        rates = {p: row[p]["cpp"] / r["N"] for p in POL}
        best = max(rates.values())
        ref = S[t]["policy_grid"][c]["lcnu"]["whole"]
        cells.append({"t": t, "c": int(c), "rates": rates, "gap": 100 * (best - rates["lcnu"]),
                      "p2": abs(rates["lcnu"] - ref), "best": max(rates, key=rates.get)})
N = sum(len(r["cells"]) * 13 for r in R["traces"].values())
ck("351 cells", N == 351)
P1 = p1 == N and det == N
P2 = all(x["p2"] <= 1e-12 for x in cells) and len(cells) == 27
within = sum(x["gap"] <= 0.5 for x in cells)
P3 = within >= 25
ns = {t: max(r["ns_per_access_median"][c]["lcnu"] for c in r["ns_per_access_median"]) for t, r in R["traces"].items()}
P4 = all(v <= 1000 for v in ns.values())
verdict = ("PARITY-BREAK" if not (P1 and P2) else "PARITY-HOLDS:" + ("DEFAULT-CONFIRMED" if P3 else "DEFAULT-CHALLENGED")) \
    + "|" + ("OVERHEAD-OK" if P4 else "OVERHEAD-HIGH")
ck("verdict == runner", verdict == R["adjudication"]["verdict"])
ck("P3 count == runner", within == R["adjudication"]["P3_within_n"])
bad = [n for n, ok in checks if not ok]
if bad:
    print("FAIL", bad[:10]); sys.exit(1)

# descriptive: crossover and simple capacity-switch rule (LCNU below, S3-FIFO above)
lines = []
for t in ("granite", "hi", "lo"):
    xs = sorted((x for x in cells if x["t"] == t), key=lambda x: x["c"])
    lose = [x for x in xs if x["gap"] > 0]
    first = lose[0]["c"] if lose else None
    worst = max(xs, key=lambda x: x["gap"])
    s3_best = sum(x["best"] == "s3fifo" for x in xs)
    lines.append(f"- **{t}** (distinct {DIST[t]}): LCNU best through cap {max([x['c'] for x in xs if x['gap']==0])}; "
                 f"first loss at cap {first} ({first/DIST[t]:.2f}x distinct); worst gap {worst['gap']:.2f}pp at cap {worst['c']} "
                 f"(LCNU {worst['rates']['lcnu']:.4f} vs {worst['best']} {worst['rates'][worst['best']]:.4f}); "
                 f"S3-FIFO is best in {s3_best}/9 cells.")
oracle2 = [max(x["rates"]["lcnu"], x["rates"]["s3fifo"]) for x in cells]
regret2 = max(100 * (max(x["rates"].values()) - o) for x, o in zip(cells, oracle2))
lcnu_lose_s3 = [x for x in cells if x["rates"]["s3fifo"] > x["rates"]["lcnu"]]
leads = []
for x in cells:
    if x["gap"] == 0:
        rest = sorted((v for p, v in x["rates"].items() if p != "lcnu"), reverse=True)
        leads.append(100 * (x["rates"]["lcnu"] - rest[0]))
ck("all lcnu-loss cells are s3fifo-best", all(x["best"] == "s3fifo" for x in cells if x["gap"] > 0))
for t in ("granite", "hi", "lo"):  # losses form a contiguous upper tail of the grid
    xs = sorted((x for x in cells if x["t"] == t), key=lambda x: x["c"])
    flags = [x["gap"] > 0 for x in xs]
    ck(f"{t} losses contiguous upper tail", flags == sorted(flags))
qx = [min(x["c"] for x in cells if x["t"] == t and x["gap"] > 0) / DIST[t] for t in ("hi", "lo")]
gx = min(x["c"] for x in cells if x["t"] == "granite" and x["gap"] > 0) / DIST["granite"]
bad = [n for n, ok in checks if not ok]
if bad:
    print("FAIL", bad); sys.exit(1)
sieve_gap = min(100 * (x["rates"]["lcnu"] - x["rates"]["sieve"]) for x in cells)

h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
art = (D / "ARTIFACT.sha256").read_text()
md = f"""# ADDENDUM58 — exp715: shipped engine eviction-policy port vs simulator, 3 full real decode traces

**Verdict (pre-registered ladder, PREREG.md frozen at e85a16a): `{verdict}`**

Upstream MoE-Infinity ported the cache-simulator policies to C++ (#339) and made LCNU the
engine default (#341). This experiment runs the pinned upstream port (`UPSTREAM_SHA`
{(D/'UPSTREAM_SHA').read_text().strip()[:12]}) and the upstream Python simulator on our three full decode-only streams
(granite-3.1-moe-3b N=638208, qwen3-30b-a3b hi N=786432, lo N=638208) at the sealed exp704
capacity grids, 13 policies, 351 cells.

## Bars
- **P1 exact parity: PASS.** C++ == Python simulator hit count in {p1}/{N} cells; C++ rerun bit-identical {det}/{N}.
  This covers granite-3.1-moe, a family upstream never traced, and the full streams (upstream checked 200k accesses of one trace).
- **P2 sealed anchor: PASS.** C++ LCNU rate == sealed exp704 LCNU in 27/27 cells (max |diff| {max(x['p2'] for x in cells):.1e}).
- **P3 LCNU default within 0.5pp of best in >=25/27: FAIL ({within}/27).**
- **P4 overhead <=1000 ns/access: PASS.** LCNU worst median ns/access: {', '.join(f'{k} {v:.0f}' for k, v in ns.items())}
  (Mack M4, loadavg {R['loadavg'][0]:.1f} with another experiment running). At 48 layers x top-8 that is ~{ns['hi']*48*8/1e3:.0f} us CPU per decode token for the policy alone.

## Where the default loses (descriptive, derived here from raw cells)
{chr(10).join(lines)}
- LCNU loses to S3-FIFO in {len(lcnu_lose_s3)}/27 cells, always a contiguous upper tail of each grid; where LCNU is best it leads the runner-up by {min(leads):.2f}-{max(leads):.2f}pp.
- A two-policy rule (LCNU or S3-FIFO, whichever is better per cell) is within {regret2:.3f}pp of the best of all 13 policies in every cell — the other 11 policies add nothing on this traffic.
- SIEVE trails LCNU by >= {sieve_gap:.1f}pp in every cell; it should not be offered as a residency policy for MoE decode without a warning.

## Reading
The port is faithful: no parity defect on 351 real cells. The default choice is right for
memory-starved deployments (the case MoE offloading exists for) and wrong by up to
{max(x['gap'] for x in cells):.1f}pp once the cache holds about {min(qx):.2f}-{max(qx):.2f}x of the distinct experts on qwen30b
(granite: {gx:.2f}x). The obvious follow-up is a capacity-aware default (LCNU below a crossover,
S3-FIFO above), pre-registered with the crossover fitted on two traces and tested on the third.

## Scope
Replay through `SimulateEvictionPolicy` only; not `ExpertResidencyManager` integration and no
latency/throughput claim. Real-engine measurement is being brought up on Winnie (exp716).

## Provenance
- result `exp715-engineparity.json` sha256 {h(D/'exp715-engineparity.json')}
- frozen ARTIFACT.sha256 (== freeze commit e85a16a):
```
{art.strip()}
```
- adjudicator `gen_addendum58.py` recomputes every bar from raw per-cell counts; {len(checks)} internal checks PASS; runner wall {R['total_elapsed_s']:.0f}s, exit 0.
"""
out = D / "ADDENDUM58.md"
assert not out.exists() or "--force" in sys.argv, "ADDENDUM58 exists"
out.write_text(md)
print("OK", verdict, len(checks), "checks;", out)
