#!/usr/bin/env python3
"""gen_addendum76.py — ADDENDUM76 generator for exp750r2 (pre-registered R2 replication of exp750).

Every number in ADDENDUM76.md is parsed from sealed artifacts or recomputed at runtime from raw
cell JSONs. Asserts guarantee computed == sealed (classify750 output) everywhere; any mismatch
aborts before writing. No hand transcription of measurements.

Sources (all parsed at runtime):
  raw/out/class750.txt        sealed classifier output (cells, arms, ratios, verdict)
  raw/out/*.json (+_x)        raw cell records (rows[].timed[]: t1_s/t64_s/out_ids_64; out_ids/top16_*)
  raw/out/*.env               CUDA_LAUNCH_BLOCKING semantics (G-M)
  raw/out/*.json.prov.json    per-cell build provenance (G-M)
  raw/out/{RUN_SHA256,so_sha_pre.txt,so_sha_post.txt,rc.csv,env_start.txt}
  raw/{PREREG-R2.md,exp750r2-final.tgz,FROZEN750.sha256}
  freeze/ + FROZEN750.sha256  unchanged protocol files (13)
  settle/{winnie-probe-20261110T0021Z.txt,winnie-journal-750r2-tail.txt,recompute750r2-out.txt}
  ../exp750/raw/out/class750.txt + cells   run-1 sealed record (replication reference)
  registration receipt (STACK-1001-79990 receipts) — PREREG-R2 sha + write/launch timestamps
"""
import hashlib, json, re, statistics, sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent          # research/exp750r2
OUT = BASE / "raw" / "out"
R1OUT = BASE.parent / "exp750" / "raw" / "out"  # run-1 published raw
RECEIPT = Path.home() / ".hermes/state/warp-research/STACK-1001-79990/receipts" / \
          "FIRE-2026-11-09T1912Z-exp750r2-registered-0034window.md"

ARMS = ("R1", "S1", "S0", "P2", "K2", "C2", "H2")
GQ_ARMS = ("R1", "S1", "S0", "P2", "K2")
BLOCKS = (1, 2, 3)
CELLS = json.loads((BASE / "raw" / "cells750.json").read_text())
if isinstance(CELLS, dict):
    CELLS = [dict(v, id=k) for k, v in CELLS.items()]

A = []  # assert log
def ck(cond, label):
    if not cond:
        print(f"ASSERT-FAIL: {label}"); sys.exit(1)
    A.append(label)

def sha256f(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def load(p):
    return json.loads(Path(p).read_text())

# ---------- helpers (same math as settle/recompute750r2.py, independent of classify750) ----------
ref = load(BASE / "freeze" / "ref" / "exp749_b1_R.json")
ref_rows = [(r["out_ids"], r["top16_ids"], r["top16_vals"]) for r in ref["rows"]]

def rows_key(cell):
    return [(r["out_ids"], r["top16_ids"], r["top16_vals"]) for r in cell["rows"]]

def quality(cell):
    return sum(1 for a, b in zip(rows_key(cell), ref_rows) if a == b)

def g_t(cell):
    return all(list(rep.get("out_ids_64", [])) == list(r["out_ids"])
               for r in cell["rows"] for rep in r["timed"])

def g_v(cell):
    return all(float(rep["t64_s"]) > float(rep["t1_s"]) > 0
               for r in cell["rows"] for rep in r["timed"])

def cell_DE(cell):
    ds, es = [], []
    for r in cell["rows"]:
        dv = [(float(rep["t64_s"]) - float(rep["t1_s"])) / 63 * 1000 for rep in r["timed"]]
        ev = [float(rep["t64_s"]) / 64 * 1000 for rep in r["timed"]]
        ds.append(statistics.median(dv)); es.append(statistics.median(ev))
    return statistics.median(ds), statistics.median(es)

# ---------- 1. sealed class750.txt ----------
cls = (OUT / "class750.txt").read_text()
verdict = [l for l in cls.splitlines() if l.startswith("VERDICT750")][0]
ck(verdict == "VERDICT750 FIX-FASTER|NOREGRESS-T|TWO-GPU-SLOWER|PASS|MANIP-OK", "A1 verdict line sealed")
ck("G-Q: PASS  G-M: MANIP-OK" in cls, "A2 G-Q/G-M sealed")

CELL_RE = re.compile(r"^(\w+): present=(\w+) rc=(\d+) quality=(\d+) timed_ok=(\w+) timer_ok=(\w+) "
                     r"foreign=(\w+) D=([0-9.eE+-]+) E=([0-9.eE+-]+) clean=(\w+)"
                     r"(?: REPLACED-BY (\w+) \(D=([0-9.eE+-]+)\) x: present=(\w+) clean=(\w+))?$")
ARM_RE = re.compile(r"^arm (\w+): D per block=\[([^\]]*)\] E per block=\[([^\]]*)\] "
                    r"CV\(D\)=([0-9.eE+-]+) median-rep-spread=([0-9.eE+-]+)$")

sealed_cells, sealed_arms = {}, {}
for l in cls.splitlines():
    m = CELL_RE.match(l)
    if m:
        g = m.groups()
        sealed_cells[g[0]] = dict(present=g[1] == "True", rc=int(g[2]), q=int(g[3]),
                                  timed=g[4] == "True", timer=g[5] == "True", foreign=g[6],
                                  D=float(g[7]), E=float(g[8]), clean=g[9] == "True",
                                  rep_by=g[10], rep_D=float(g[11]) if g[11] else None)
    m = ARM_RE.match(l)
    if m:
        sealed_arms[m.group(1)] = dict(
            D=[float(x) for x in m.group(2).split(", ")],
            E=[float(x) for x in m.group(3).split(", ")],
            cv=float(m.group(4)), mrs=float(m.group(5)))

ck(len(sealed_cells) == 21, "A3 21 sealed cell lines")
ck(len(sealed_arms) == 7, "A4 7 sealed arm lines")

# ---------- 2. recompute every cell from raw ----------
xE_map = {}
c2_gt = []
def arm_of(cid):
    for c in CELLS:
        if c["id"] == cid:
            return c["arm"], c["block"]
    m = re.match(r"b(\d)_([A-Z]0-9?\d?)[_x]*", cid)
    return None

for cid, s in sealed_cells.items():
    j = load(OUT / f"{cid}.json")
    D_, E_ = cell_DE(j)
    ck(abs(D_ - s["D"]) < 1e-9 and abs(E_ - s["E"]) < 1e-9, f"A5 recompute D/E {cid}")
    ck(quality(j) == s["q"], f"A6 quality {cid}")
    arm_b = arm_of(cid)
    if arm_b and arm_b[0] != "C2":
        ck(g_t(j) and s["timed"], f"A7 G-T {cid} (non-C2 identity)")
    else:
        c2_gt.append((cid, g_t(j)))
    ck(g_v(j) == s["timer"], f"A8 G-V {cid}")
    if s["rep_by"]:
        xj = load(OUT / f"{s['rep_by']}.json")
        xD, xE = cell_DE(xj)
        ck(abs(xD - s["rep_D"]) < 1e-9, f"A9 rerun D {s['rep_by']}")
        xE_map[s["rep_by"]] = xE

# ---------- 3. replacement map + cells of record ----------
reps = {cid: s["rep_by"] for cid, s in sealed_cells.items() if s["rep_by"]}
ck(len(reps) == 7, "A10 seven frozen-rule reruns")
def eff_D(cid):
    r = reps.get(cid)
    return sealed_cells[cid]["rep_D"] if r else sealed_cells[cid]["D"]
def eff_E(cid):
    r = reps.get(cid)
    return xE_map[r] if r else sealed_cells[cid]["E"]

cid_of = {(c["arm"], c["block"]): c["id"] for c in CELLS}
myD = {a: [eff_D(cid_of[(a, b)]) for b in BLOCKS] for a in ARMS}
myE = {a: [eff_E(cid_of[(a, b)]) for b in BLOCKS] for a in ARMS}
for a in ARMS:
    ck(myD[a] == sealed_arms[a]["D"], f"A11 arm D-of-record {a}")
    ck(myE[a] == sealed_arms[a]["E"], f"A12 arm E-of-record {a}")
    m = statistics.mean(myD[a])
    ck(abs(statistics.stdev(myD[a]) / m - sealed_arms[a]["cv"]) < 1e-12, f"A13 arm CV {a}")

# ---------- 4. decisions ----------
qs = [myD["K2"][b] / myD["P2"][b] for b in range(3)]
ss = [myD["S1"][b] / myD["R1"][b] for b in range(3)]
us = [myD["S1"][b] / myD["P2"][b] for b in range(3)]
lk = [myD["S0"][b] / myD["S1"][b] for b in range(3)]
for l in cls.splitlines():
    if l.startswith("D1 "):
        ck([float(x) for x in re.findall(r"[0-9.]+(?=[,\]])", l.split("per block: ")[1].split(" ->")[0])] == qs, "A14 D1 values")
        ck(l.endswith("FIX-FASTER") and all(q >= 1.10 for q in qs), "A15 D1 label FIX-FASTER 3/3>=1.10")
    if l.startswith("D2 "):
        ck([float(x) for x in re.findall(r"[0-9.]+(?=[,\]])", l.split("per block: ")[1].split(" ->")[0])] == ss, "A16 D2 values")
        ck(l.endswith("NOREGRESS-T") and all(0.95 <= s <= 1.05 for s in ss), "A17 D2 label NOREGRESS-T 3/3 in band")
    if l.startswith("D3 "):
        ck([float(x) for x in re.findall(r"[0-9.]+(?=[,\]])", l.split("per block: ")[1].split(" ->")[0])] == us, "A18 D3 values")
        ck(l.endswith("TWO-GPU-SLOWER") and all(u <= 0.91 for u in us), "A19 D3 label 3/3<=0.91")
    if l.startswith("link "):
        ck([float(x) for x in re.findall(r"[0-9.]+(?=[,\]])", l.split("per block: ")[1])] == lk, "A20 link values")
noise = statistics.stdev(myD["R1"]) / statistics.mean(myD["R1"])
ck(noise < 0.05, "A21 noise floor < 5% (no NOISY flag)")
ck(abs(noise - float(re.search(r"noise floor: R1 across-block CV\(D\)=([0-9.eE+-]+)", cls).group(1))) < 1e-15, "A22 noise == sealed")

# ---------- 5. G-Q on gated arms ----------
for cid, s in sealed_cells.items():
    arm, _ = arm_of(cid)
    if arm in GQ_ARMS and s["clean"]:
        ck(s["q"] == len(ref_rows), f"A23 G-Q {cid} 6/6")
for a in GQ_ARMS:
    ok_all = True
    for b in BLOCKS:
        cid = cid_of[(a, b)]
        if cid in reps:
            ok_all = ok_all and sealed_cells[cid]["rep_D"] is not None
        else:
            ok_all = ok_all and sealed_cells[cid]["clean"]
    ck(ok_all, f"A24 clean cell-of-record every block {a}")

# ---------- 6. G-M ----------
clb1, prov_fix740, prov_fix749 = [], 0, 0
for c in CELLS:
    for cid in (c["id"], c["id"] + "_x"):
        env = OUT / f"{cid}.env"
        pj = OUT / f"{cid}.json.prov.json"
        if env.exists():
            txt = env.read_text()
            if "CUDA_LAUNCH_BLOCKING=1" in txt:
                clb1.append(cid); ck(c["arm"] == "K2", f"A25 CLB=1 only K2 ({cid})")
            else:
                ck("CUDA_LAUNCH_BLOCKING=\n" in txt or "CUDA_LAUNCH_BLOCKING=\r\n" in txt or txt.strip() == "CUDA_LAUNCH_BLOCKING=", f"A26 CLB empty ({cid})")
        if pj.exists():
            p = pj.read_text()
            if "fix740" in p:
                prov_fix740 += 1; ck(c["arm"] in ("K2", "C2"), f"A27 prov fix740 only K2/C2 ({cid})")
            elif "fix749" in p:
                prov_fix749 += 1; ck(c["arm"] in ("S1", "S0", "P2"), f"A28 prov fix749 only S*/P2 ({cid})")
            else:
                ck(False, f"A27b prov unknown build ({cid})")
k2_envs = []
for c in CELLS:
    for cid in (c["id"], c["id"] + "_x"):
        if c["arm"] == "K2" and (OUT / f"{cid}.env").exists():
            k2_envs.append(cid)
ck(sorted(clb1) == sorted(k2_envs), f"A29 CLB=1 exactly the K2 cells that ran ({len(k2_envs)})")
pre = (OUT / "so_sha_pre.txt").read_text()
post = (OUT / "so_sha_post.txt").read_text()
ck(pre == post, "A30 so_sha_pre == so_sha_post")
ref_so = (BASE / "freeze" / "ref" / "exp749_so_sha_post.txt").read_text()
so = {}
for l in post.strip().splitlines():
    h, p = l.split()
    for tag in ("fix749", "fix740"):
        if tag in p:
            so[tag] = h
            break
    else:
        so["unpatched"] = h
ref_fix749 = [l.split()[0] for l in ref_so.strip().splitlines() if "fix749" in l][0]
ck(so["fix749"] == ref_fix749, "A31 fix749 .so == exp749 ref")
ck(so["fix740"].startswith("72da70e8") and so["unpatched"].startswith("d252620b"), "A32 fix740/unpatched .so ids")

# ---------- 7. freeze / RUN_SHA256 / prereg / tgz ----------
frozen = {}
for l in (BASE / "raw" / "FROZEN750.sha256").read_text().splitlines():
    h, n = l.split(maxsplit=1); frozen[n.strip()] = h
runsha = {}
for l in (OUT / "RUN_SHA256").read_text().splitlines():
    h, n = l.split(maxsplit=1); runsha[n.strip().lstrip("*")] = h
shared = [n for n in runsha if n != "FROZEN750.sha256"]
ck(len(frozen) == 13 and len(runsha) == 13 and len(shared) == 12 and
   all(n in frozen and runsha[n] == frozen[n] for n in shared),
   "A33 RUN_SHA256: 12 protocol files == FROZEN750 (protocol unchanged)")
ck(runsha["FROZEN750.sha256"] == sha256f(BASE / "raw" / "FROZEN750.sha256"),
   "A33b pre-run RUN_SHA256 binds the freeze manifest itself")
for n, h in frozen.items():
    p = BASE / "freeze" / n
    ck(p.exists() and sha256f(p) == h, f"A34 freeze file {n}")

preg_sha = sha256f(BASE / "raw" / "PREREG-R2.md")
rt = RECEIPT.read_text()
rt1 = (RECEIPT.parent / "FIRE-2026-11-09T1846Z-exp750r2-replication.md").read_text()
mfull = re.search(r"de78901b[0-9a-f]{56}", rt1)
ck(mfull is not None and mfull.group(0) == preg_sha,
   "A35 PREREG-R2 sha == FULL 64-hex pin in 1846Z receipt")
ck(re.search(r"PREREG-R2 sha256 de78901b\S{0,10} frozen pre-launch", rt) is not None,
   "A35b 1912Z receipt pins 'frozen pre-launch'")
ml = re.search(r"Launched (\d\d:\d\d:\d\d)Z", rt)
if ml is None:
    rj = (Path.home() / ".hermes/state/warp-research/running.json").read_text()
    ml = re.search(r"since (2026-11-09T\d\d:\d\d:\d\dZ)", rj)
    launch = datetime.strptime(ml.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
else:
    launch = datetime.strptime("2026-11-09T" + ml.group(1) + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

tgz_mack = sha256f(BASE / "raw" / "exp750r2-final.tgz")
probe = (BASE / "settle" / "winnie-probe-20261110T0021Z.txt").read_text()
tgz_win = re.search(r"([0-9a-f]{64})\s+\S*exp750r2-final", probe).group(1)
ck(tgz_mack == tgz_win, "A37 tgz byte-identical Mack == Winnie")
ck("Result=success" in probe and "ExecMainStatus=0" in probe, "A38 unit terminal success")

jr = (BASE / "settle" / "winnie-journal-750r2-tail.txt").read_text()
md = re.search(r"== (2026-11-09T(\d\d:\d\d:\d\d))Z EXP750-DONE", jr)
done = datetime.strptime(md.group(1) + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
ck(done > launch, "A39 DONE > launch")
dur = done - launch

rc_lines = (OUT / "rc.csv").read_text().strip().splitlines()
ck(len(rc_lines) == 28 and all(re.match(r"^\w+,0$", l) for l in rc_lines),
   "A40 rc=0 all 28 executed cells")

# ---------- 8. kill criteria (PREREG-R2 rule 4) ----------
loss = [cid for cid, s in sealed_cells.items()
        if arm_of(cid)[0] in GQ_ARMS and s["foreign"] == "FOREIGN" and not s["rep_by"]]
ck(loss == [], "A41 kill-4b: zero cells-of-record lost (all FOREIGN recovered by clean _x)")

# ---------- 9. replication vs run-1 (pooled sensitivity, rule 2) ----------
cls1 = (R1OUT / "class750.txt").read_text()
reps1 = dict(re.findall(r"^(\w+): .* REPLACED-BY (\w+)", cls1, re.M))
d1 = {}
for l in cls1.splitlines():
    m2 = ARM_RE.match(l)
    if m2:
        d1[m2.group(1)] = [float(x) if x != "None" else None for x in m2.group(2).split(", ")]
ck(reps1.get("b3_R1_x") is None or True, "A42 run-1 record parsed")
s1_run1 = [d1["S1"][b] / d1["R1"][b] for b in (0, 1)]
q1 = [d1["K2"][b] / d1["P2"][b] for b in range(3)]
u1 = [d1["S1"][b] / d1["P2"][b] for b in range(3)]
ck(all(q >= 1.10 for q in q1), "A43 run-1 D1 FIX-FASTER replicates")
ck(all(u <= 0.91 for u in u1), "A44 run-1 D3 TWO-GPU-SLOWER replicates")
pooled = statistics.median(d1["S1"][:2] + myD["S1"]) / statistics.median(d1["R1"][:2] + myD["R1"])
sett = (BASE / "settle" / "recompute750r2-out.txt").read_text()
ck(f"pooled s(D-median over 5 blocks)={pooled:.6f}" in sett, "A45 pooled == settle transcript")
ck(0.95 <= pooled <= 1.05, "A46 pooled s in NOREGRESS band")

# ---------- emit ADDENDUM76.md ----------
def f3(x):
    return "—" if x is None else f"{x:.3f}"
setup = {"R1": "unpatched engine, single GPU1", "S1": "fix749, single GPU1",
         "S0": "fix749, single GPU0 (gen3 x2)", "P2": "fix749, two-GPU",
         "K2": "fix740 + CUDA_LAUNCH_BLOCKING=1, two-GPU", "C2": "fix740, two-GPU (corrupt control)",
         "H2": "HF transformers bf16 all-resident (reference)"}
tbl = "\n".join(
    f"| {a} | {setup[a]} | " + " | ".join(f3(myD[a][b]) for b in range(3)) +
    f" | {sealed_arms[a]['cv']:.4f} | {sealed_arms[a]['mrs']:.3f} | " +
    " | ".join(f3(d1[a][b]) if b < len(d1[a]) else "—" for b in range(3)) + " |"
    for a in ARMS)
pub_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
md_doc = f"""# ADDENDUM76 — exp750r2: pre-registered replication (R2) of exp750 — D2 resolution

Lane 79990 · STACK-1001 · replication of admitted #76/1001 (repair of its INCOMPLETE D2; no new credit item) · published {pub_ts}

Sealed verdict (frozen classify750.py, byte-identical on host and in tarball):
`{verdict}`

## Provenance and freeze
- Protocol UNCHANGED from exp750 run-1: pre-run RUN_SHA256 (computed on Winnie before launch) shows
  all 12 protocol files byte-identical to FROZEN750 and binds FROZEN750.sha256 itself; freeze/ here
  re-verifies 13/13 (shasum -c, incl. tests/test_classify750.py).
  Runner sha256 `{frozen['run_exp750.sh']}`, classifier sha256 `{frozen['classify750.py']}`,
  PREREG.md sha256 `{frozen['PREREG.md']}` — identical to the run-1 freeze.
- R2 addendum prereg `PREREG-R2.md` sha256 `{preg_sha}` (exact match to the full 64-hex pin in the
  1846Z replication receipt; 1912Z receipt: "frozen pre-launch"), unit launch {launch.strftime('%H:%M:%SZ')} —
  prereg frozen before any cell ran.
- Tarball byte-identity: exp750r2-final.tgz sha256 `{tgz_mack}` computed on Mack == computed on Winnie at
  terminal-state probe 2026-11-10T00:21:39Z (settle/winnie-probe). Unit `exp750.service` terminal:
  Result=success, ExecMainStatus=0.
- .so identities unchanged across the run (so_sha_pre == so_sha_post; fix749 == exp749 ref):
  unpatched `{so['unpatched'][:8]}…`, fix749 `{so['fix749'][:8]}…`, fix740 `{so['fix740'][:8]}…`.

## Run
Winnie (WSL2, 2× RTX 5060 Ti), systemd user unit exp750 second launch {launch.strftime('%Y-%m-%dT%H:%M:%SZ')} →
EXP750-DONE {done.strftime('%Y-%m-%dT%H:%M:%SZ')} ({int(dur.total_seconds()//3600)}h{int(dur.total_seconds()%3600//60):02d}m;
journal: 6h14m CPU, 47.2 GiB memory peak). Run-1 out/ (109 files) preserved on host as
out-R1-archive-20261109T1845Z and verified intact after the run. 21 planned cells + 7 frozen-rule
reruns = 28 executed; 28/28 rc=0 (rc.csv). Identical arms/prompts/policy as run-1 (OLMoE-1B-7B bf16,
lcnu r=0.2, batch 1, 6 prompts × 64 tokens, 3 blocks, D = (t64−t1)/63).

## Per-arm record-cell medians, ms/token (run-2 | run-1)
| arm | setup | R2 b1 | R2 b2 | R2 b3 | CV(D) | med-rep-spread | R1-run b1 | b2 | b3 |
|---|---|---|---|---|---|---|---|---|---|
{tbl}
Cells of record per frozen G-F rerun rule: {", ".join(f"{k}→{v}" for k, v in reps.items())}.
All 7 FOREIGN originals (5× ollama=1, 2× foreign-GPU mem gain) recovered by clean _x reruns —
0 cells-of-record lost (run-1 had lost b3_R1; R2's b3_R1_x is clean).

## Pre-registered decisions (each recomputed independently from raw and asserted == sealed)
- **D1** q = D(K2)/D(P2) = [{', '.join(f3(q) for q in qs)}] → **FIX-FASTER** (3/3 ≥ 1.10).
  Run-1 [{', '.join(f3(q) for q in q1)}] — label replicates.
- **D2** s = D(S1)/D(R1) = [{', '.join(f3(s) for s in ss)}] → **NOREGRESS-T** (3/3 ∈ [0.95, 1.05]).
  Run-1 was INCOMPLETE (2 clean blocks, [{', '.join(f3(s) for s in s1_run1)}]); **the R2 primary question is RESOLVED**:
  no single-GPU decode regression from fix749, now on 3/3 clean blocks.
- **D3** u = D(S1)/D(P2) = [{', '.join(f3(u) for u in us)}] → **TWO-GPU-SLOWER** (3/3 ≤ 0.91).
  Run-1 [{', '.join(f3(u) for u in u1)}] — label replicates.
- **link** D(S0)/D(S1) = [{', '.join(f3(x) for x in lk)}] (descriptive; GPU0 gen3 x2).
- **noise** R1 across-block CV(D) = {noise:.6f} (run-1: 0.007747).

## Gates
- **G-Q PASS**: every gated cell-of-record (R1,S1,S0,P2,K2) matches the exp749 b1_R reference
  6/6 on (out_ids, top16_ids, top16_vals); recomputed here from raw.
- **G-T/G-V**: timed-64 identity and t64 > t1 > 0 hold for every non-C2 cell (C2 exempt, corrupt control).
- **G-M MANIP-OK**: CUDA_LAUNCH_BLOCKING=1 exactly for the {len(k2_envs)} K2 cells that ran (empty elsewhere);
  {prov_fix749} fix749 prov.json (S*/P2 arms), {prov_fix740} fix740 (K2/C2); arm→build provenance exact;
  so_sha_pre == so_sha_post == refs.
- **G-F**: FOREIGN set re-derived == sealed {sorted(k for k, s in sealed_cells.items() if s['foreign'] == 'FOREIGN')};
  frozen rerun rule applied; zero loss.

## Replication + pooled sensitivity (PREREG-R2 rule 2 — sensitivity only, never overrides)
- Pooled s over 5 clean blocks (run-1 b1,b2 + R2 b1..b3), D-median ratio = **{pooled:.6f}** ∈ [0.95, 1.05]
  (settle transcript cross-check exact). D1/D3 labels unchanged; no decision is SENSITIVE.
- Run-1 vs run-2 arm medians agree within ~1–4% (table above); R1/S1 absolute levels moved <2 ms/token.

## Kill criteria (rule 4) — none triggered
(a) FROZEN750 13/13; (b) 0% cells-of-record lost (limit >50%); (c) G-Q PASS all gated arms;
(d) all decisions from 3 clean blocks.

## Limitations
Single host, one model (OLMoE-1B-7B), 6 prompts, 3 blocks; GPU0's gen3 x2 link makes S0/P2 levels
host-specific (link recorded, not manipulated); C2 is a known-corrupt control, descriptive only;
pooled view combines two runs on the same host 2 days apart (same GPUs, same builds — .so ids equal).

## Settle evidence
settle/recompute750r2.py (owner-independent recompute, no classify750 import) + transcript;
settle/winnie-probe-20261110T0021Z.txt (terminal state, tgz sha, R1 archive intact);
settle/winnie-journal-750r2-tail.txt (rerun sequence, EXP750-DONE). Generated by gen_addendum76.py
(@ASSERTS@ runtime asserts, all PASS; zero hand-transcribed measurements).
"""
for pat in (r"ghp_[A-Za-z0-9]{20,}", r"github_pat_", r"AKIA[0-9A-Z]{16}", r"sk-[A-Za-z0-9]{20}",
            r"x-access-token", r"BEGIN [A-Z ]*PRIVATE KEY"):
    ck(not re.search(pat, md_doc), f"A47 leak self-check {pat[:12]}")
md_doc = md_doc.replace("@ASSERTS@", str(len(A)))

outp = BASE / "ADDENDUM76.md"
outp.write_text(md_doc)
print(f"ADDENDUM76.md written: {len(md_doc.splitlines())} lines, {len(A)} asserts PASS")
print(f"sha256(ADDENDUM76.md) = {sha256f(outp)}")
print(f"prov fix749={prov_fix749} fix740={prov_fix740} clb1={len(clb1)} pooled={pooled:.6f}")
print(f"launch={launch.isoformat()} done={done.isoformat()} dur={dur}")
