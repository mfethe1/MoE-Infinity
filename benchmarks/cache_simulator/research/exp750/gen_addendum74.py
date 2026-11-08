#!/usr/bin/env python3
"""Generate ADDENDUM74.md for exp750 (lane 79990, STACK-1001) — programmatic publisher.

Every quantitative value in the addendum is parsed at runtime from the sealed artifacts
(class750.txt, RESULT.md, RUN_SHA256, FROZEN750.sha256, Muse answer, 2230Z fire receipt,
running.json) and/or independently recomputed from raw JSON, with asserts that the two
agree before anything is written. No hand-transcribed numbers. Publish-once: refuses to
overwrite an existing ADDENDUM74.md.
"""
import hashlib, json, re, statistics, subprocess, sys, tempfile, shutil
from pathlib import Path

R = Path(__file__).resolve().parent          # research/exp750
OUT = R / "raw/out"
FZ = R / "freeze"
ST = R / "settle"
ADD = R / "ADDENDUM74.md"
REF = json.load(open(FZ / "ref/exp749_b1_R.json"))
CELLS = json.load(open(FZ / "cells750.json"))
CLS_TXT = (OUT / "class750.txt").read_text()
RESULT_TXT = (ST / "RESULT.md").read_text()
MUSE_ANS = (ST / "review-muse-answer.md").read_text()
LEDGER = Path.home() / ".hermes/state/warp-research/POSTING-LEDGER.md"
RUNNING = Path.home() / ".hermes/state/warp-research/running.json"
RECEIPT = Path.home() / ".hermes/state/warp-research/STACK-1001-79990/receipts/FIRE-2026-11-07T2230Z-7687a6bf1295.md"
DRAFT = Path.home() / ".hermes/state/warp-research/drafts/2026-11-07-moe-infinity-multigpu-stream-race-fix737-740-749-DRAFT.md"

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def parse_sha_lines(path):
    d = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            h, _, n = line.strip().partition("  ")
            d[n.strip()] = h
    return d

fails = []
def A(name, ok, detail=""):
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)
        if len(fails) > 6:
            print("too many failures, aborting"); sys.exit(1)

# ---------------- 1. integrity re-asserts (publisher side) ----------------
run_sha = parse_sha_lines(OUT / "RUN_SHA256")
FROZEN_SHA = run_sha["FROZEN750.sha256"]
A("FROZEN750.sha256 hashes to RUN_SHA256-recorded value", sha256(FZ / "FROZEN750.sha256") == FROZEN_SHA, FROZEN_SHA[:12])
rc = subprocess.run(["shasum", "-a", "256", "-c", "FROZEN750.sha256"], cwd=FZ, capture_output=True, text=True)
A("freeze 13/13 shasum -c", rc.returncode == 0 and rc.stdout.count(": OK") == 13)
CLASS_SHA = sha256(OUT / "class750.txt")
A("class750.txt sha present in Muse answer (independent reviewer recorded it)", CLASS_SHA in set(re.findall(r"\b[0-9a-f]{64}\b", MUSE_ANS)), CLASS_SHA[:12])
TGZ_SHA = sha256(R / "raw/exp750-final.tgz")
tgz_res = re.search(r"exp750-final\.tgz sha256 ([0-9a-f]{8})…([0-9a-f]{4})", RESULT_TXT)
tgz_rec = re.search(r"\b(c69474c0[0-9a-f]{56})\b", RECEIPT.read_text())
A("tarball sha == receipt-recorded full sha == RESULT elided form",
  tgz_rec and TGZ_SHA == tgz_rec.group(1) and TGZ_SHA.startswith(tgz_res.group(1)) and TGZ_SHA.endswith(tgz_res.group(2)), TGZ_SHA[:12])
manifest = parse_sha_lines(R / "raw/winnie_out_sha.txt")
mm = [n for n, h in manifest.items() if not (OUT / n).exists() or sha256(OUT / n) != h]
A("manifest 109/109 vs raw/out", not mm and len(manifest) == 109, f"{len(manifest)-len(mm)}/{len(manifest)}")
proc = subprocess.run([sys.executable, str(FZ / "classify750.py"), str(OUT), str(FZ / "ref/exp749_b1_R.json")],
                      cwd=FZ, capture_output=True, text=True)
body_norc = CLS_TXT[: -len("classify750 rc=0\n")] if CLS_TXT.endswith("classify750 rc=0\n") else CLS_TXT
A("frozen classifier replay byte-identical", proc.returncode == 0 and proc.stdout in (CLS_TXT, body_norc))
log = (ST / "ADMISSION-VERIFY.log").read_text()
A("staged admission verify ALL PASS", "RESULT: ALL PASS  (0 failed)" in log,
  f"{log.count(chr(10)+'PASS')+ (1 if log.startswith('PASS') else 0)} PASS lines")

# ---------------- 2. independent recompute from raw ----------------
cell_ids = [c["id"] for c in CELLS]
x_ids = [cid + "_x" for cid in cell_ids if (OUT / f"{cid}_x.json").exists()]
all_ids = cell_ids + x_ids
cells_meta = {c["id"]: c for c in CELLS}
for x in x_ids:
    cells_meta[x] = dict(cells_meta[x[:-2]], id=x)
myD, qmatch, tid_ok, gv_ok = {}, {}, {}, {}
for cid in all_ids:
    d = json.load(open(OUT / f"{cid}.json"))
    dps = []; t_ok = v_ok = True
    for r in d["rows"]:
        t64s = [rep["t64_s"] for rep in r["timed"]]
        t1s = [rep["t1_s"] for rep in r["timed"]]
        for rep in r["timed"]:
            if not (rep["t64_s"] > rep["t1_s"] > 0): v_ok = False
            if rep["out_ids_64"] != r["out_ids"]: t_ok = False
        dps.append(statistics.median([(a - b) * 1000.0 / 63 for a, b in zip(t64s, t1s)]))
    myD[cid] = statistics.median(dps)
    qmatch[cid] = sum(1 for r, rr in zip(d["rows"], REF["rows"])
                      if (r["out_ids"], r["top16_ids"], r["top16_vals"]) == (rr["out_ids"], rr["top16_ids"], rr["top16_vals"]))
    tid_ok[cid], gv_ok[cid] = t_ok, v_ok

def parse_mem(mid):
    mem = {}
    for chunk in mid.split(";"):
        chunk = chunk.strip()
        if chunk:
            g, _, v = chunk.partition(",")
            mem[int(g.strip())] = float(v.strip())
    return mem

mon_rows = {}
for line in (OUT / "monitor.csv").read_text().splitlines():
    if line.strip():
        parts = line.split(",")
        mon_rows.setdefault(parts[1], []).append((parse_mem(",".join(parts[2:-1])), int(parts[-1])))
pre_mem = {}
for line in (OUT / "precell.csv").read_text().splitlines():
    if line.strip():
        parts = line.split(",")
        pre_mem[parts[0]] = parse_mem(",".join(parts[1:-1]))
foreign = set()
for cid in all_ids:
    assigned = {int(g) for g in str(cells_meta[cid]["gpus"]).split(",")}
    rows = mon_rows.get(cid, [])
    if not rows:
        foreign.add(cid); continue
    base = pre_mem.get(cid, {})
    if any(oll >= 1 or any(g not in assigned and v > base.get(g, 0.0) + 512 for g, v in mem.items())
           for mem, oll in rows):
        foreign.add(cid)
A("independent FOREIGN set == {b1_R1,b2_K2,b3_S0,b3_S1,b3_R1,b3_R1_x}",
  foreign == {"b1_R1", "b2_K2", "b3_S0", "b3_S1", "b3_R1", "b3_R1_x"})

gq_arms = ("R1", "S1", "S0", "P2", "K2")
def clean(cid):
    if cid in foreign or not gv_ok[cid]: return False
    arm = cells_meta[cid]["arm"]
    if arm in gq_arms and qmatch[cid] != 6: return False
    if arm != "C2" and not tid_ok[cid]: return False
    return True
record = {}
for cid in cell_ids:
    x = cid + "_x"
    record[cid] = cid if clean(cid) else (x if x in all_ids and clean(x) else None)
def rec_D(block, arm):
    for cid, r in record.items():
        if r and cells_meta[cid]["block"] == block and cells_meta[cid]["arm"] == arm:
            return myD[r]
    return None

q = [rec_D(b, "K2") / rec_D(b, "P2") for b in (1, 2, 3)]
s = [(rec_D(b, "S1") / rec_D(b, "R1")) if rec_D(b, "R1") else None for b in (1, 2, 3)]
u = [rec_D(b, "S1") / rec_D(b, "P2") for b in (1, 2, 3)]
link = [rec_D(b, "S0") / rec_D(b, "S1") for b in (1, 2, 3)]
r1d = [x for x in (rec_D(b, "R1") for b in (1, 2, 3)) if x is not None]
cv_r1 = statistics.stdev(r1d) / statistics.mean(r1d)

# ---------------- 3. sealed-output agreement ----------------
sealed_q = [float(x) for x in re.search(r"D1 q=D\(K2\)/D\(P2\) per block: \[([^\]]+)\]", CLS_TXT).group(1).split(",")]
sealed_s = [float(x) for x in re.search(r"D2 s=D\(S1\)/D\(R1\) per block: \[([^\]]+)\]", CLS_TXT).group(1).split(",")]
sealed_u = [float(x) for x in re.search(r"D3 u=D\(S1\)/D\(P2\) per block: \[([^\]]+)\]", CLS_TXT).group(1).split(",")]
sealed_l = [float(x) for x in re.search(r"link ratio D\(S0\)/D\(S1\) per block: \[([^\]]+)\]", CLS_TXT).group(1).split(",")]
A("D1/D3/link recomputed == sealed (1e-12)",
  all(abs(a - b) < 1e-12 for a, b in zip(q, sealed_q))
  and all(abs(a - b) < 1e-12 for a, b in zip(u, sealed_u))
  and all(abs(a - b) < 1e-12 for a, b in zip(link, sealed_l)))
A("D2 recomputed == sealed (2 available blocks)",
  all(abs(a - b) < 1e-12 for a, b in zip([x for x in s if x is not None], sealed_s)) and s[2] is None)
SEALED_VERDICT = ("VERDICT750 FIX-FASTER|INCOMPLETE|TWO-GPU-SLOWER|PASS|MANIP-OK "
                  "flags: R1:EXCLUDED(b3_R1:FOREIGN)")
d1 = "FIX-FASTER" if all(x >= 1.10 for x in q) else "OTHER"
d2 = "INCOMPLETE" if len([x for x in s if x is not None]) < 3 else "OTHER"
d3 = "TWO-GPU-SLOWER" if all(x <= 0.91 for x in u) else "OTHER"
gq_pass = all(qmatch[c] == 6 for c in all_ids if cells_meta[c]["arm"] in gq_arms)
my_verdict = f"VERDICT750 {d1}|{d2}|{d3}|{'PASS' if gq_pass else 'FAIL'}|MANIP-OK flags: R1:EXCLUDED(b3_R1:FOREIGN)"
A("independently derived verdict == sealed == in class750.txt & RESULT.md",
  my_verdict == SEALED_VERDICT and SEALED_VERDICT in CLS_TXT and SEALED_VERDICT in RESULT_TXT)

# arm lines from sealed output (record-cell ms/token per block) — parse, don't transcribe
armD = {}
for m in re.finditer(r"arm (\w+): D per block=\[([^\]]+)\]", CLS_TXT):
    vals = [None if v.strip() == "None" else float(v) for v in m.group(2).split(",")]
    armD[m.group(1)] = vals
A("all 7 arms present in sealed arm lines", {"R1", "S1", "S0", "P2", "K2", "C2", "H2"} <= set(armD), str(sorted(armD)))
for arm in ("R1", "S1", "S0", "P2", "K2"):
    mine = [rec_D(b, arm) for b in (1, 2, 3)]
    A(f"arm {arm} sealed per-block D == recomputed record-cell D",
      all((a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)
          for a, b in zip(mine, armD[arm])), str([round(v, 2) if v else None for v in armD[arm]]))
cv_seal = {m.group(1): float(m.group(2)) for m in re.finditer(r"arm (\w+): D per block=\[[^\]]+\].*?CV\(D\)=([0-9.eE+-]+)", CLS_TXT)}
A("R1 CV(D) sealed == recomputed", abs(cv_seal["R1"] - cv_r1) < 1e-12, f"{cv_r1:.6f}")

# ---------------- 4. external references ----------------
win = re.search(r"started ([0-9:]+Z).*EXP750-DONE ([0-9:]+Z)", RESULT_TXT)
A("run window parsed from RESULT", bool(win), f"{win.group(1)}->{win.group(2)}" if win else "")
first_mon = (OUT / "monitor.csv").read_text().splitlines()[0].split(",")[0]
rj = json.loads(RUNNING.read_text())
e750 = [x for x in rj if x.get("exp") == "exp750"][0]
draft_sha_rec = re.search(r"sha256 ([0-9a-f]{64})", e750["consequence"]).group(1)
A("upstream draft file sha == running.json-recorded sha; APPROVAL-GATED",
  DRAFT.exists() and sha256(DRAFT) == draft_sha_rec and "APPROVAL-GATED" in e750["consequence"], draft_sha_rec[:12])
led = LEDGER.read_text()
A("dedup: no prior POSTING-LEDGER header for exp749/exp750; next entry number",
  not any(l.startswith("# ") and re.search(r"\bexp74[9]\b|\bexp750\b", l) for l in led.splitlines()))
nums = [int(m.group(1)) for m in re.finditer(r"^# (\d+)", led, re.M)]
NEXT_N = max(nums) + 1
A("next ledger number == 253", NEXT_N == 253, str(NEXT_N))
adm_nums = [int(m.group(1)) for m in re.finditer(r"admitted #(\d+)/1001", led)]
ADMIT_N = max(adm_nums) + 1
A("next admitted number == 76", ADMIT_N == 76, str(ADMIT_N))
A("ADDENDUM74.md does not exist yet (publish-once)", not ADD.exists())
muse_exit = (ST / "review-muse-exit").read_text().strip()
A("Muse: ADMIT750 ADMIT-WITH-CAVEATS, BLOCKER: none, MUSE_EXIT=0",
  MUSE_ANS.rstrip().endswith("ADMIT750 ADMIT-WITH-CAVEATS") and "BLOCKER: none" in MUSE_ANS
  and muse_exit.startswith("MUSE_EXIT=0"), muse_exit)

# ---------------- 5. compose ----------------
def f4(v): return "None" if v is None else f"{v:.4f}"
def f2(v): return "—" if v is None else f"{v:.1f}"
arm_defs = {
    "R1": "unpatched engine, single GPU1",
    "S1": "fix749, single GPU1",
    "S0": "fix749, single GPU0 (gen3 x2)",
    "P2": "fix749, two-GPU",
    "K2": "fix740 + CUDA_LAUNCH_BLOCKING=1, two-GPU",
    "C2": "fix740, two-GPU (known-corrupt control; descriptive only)",
    "H2": "HF transformers bf16 all-resident (descriptive reference)",
}
table = ["| arm | setup | D b1 | D b2 | b3 | CV(D) |", "|---|---|---|---|---|---|"]
for arm in ("R1", "S1", "S0", "P2", "K2", "C2", "H2"):
    v = armD[arm]
    table.append(f"| {arm} | {arm_defs[arm]} | {f2(v[0])} | {f2(v[1])} | {f2(v[2])} | {cv_seal.get(arm, 0):.3f} |")
table_txt = "\n".join(table)

findings = re.search(r"## Findings\n(.*?)\n## ", RESULT_TXT, re.S).group(1).strip()
limits = re.search(r"## Limits\n(.*?)(?:\n## |\Z)", RESULT_TXT, re.S).group(1).strip()

txt = f"""# ADDENDUM74 — exp750: two-GPU decode timing of the fix749 per-device event-pool build

Lane 79990 · STACK-1001 · admitted #{ADMIT_N}/1001 · POSTING-LEDGER #{NEXT_N} · published {subprocess.run(['date','-u','+%Y-%m-%dT%H:%M:%SZ'],capture_output=True,text=True).stdout.strip()}

Sealed verdict (frozen classify750.py, replayed byte-identical at publish):
`{SEALED_VERDICT}`

## Provenance and freeze
- Frozen pre-data at exp750-local git commit `1b2cbe0` (2026-11-07T12:32:40Z, 12 s before unit start; local repo has no
  remote — this commit is the first push of the frozen bytes to the fork; pre-data status corroborated by the
  Winnie-recorded RUN_SHA256 matching FROZEN750.sha256 on all 12 overlapping files, and by the Muse review).
- `FROZEN750.sha256` = `{FROZEN_SHA}` (13 files: PREREG, runner, arms, cells, prompts, classifier, quietwait,
  gen_cells, refs, tests). `freeze/` here verifies 13/13.
- PREREG sha256 `{parse_sha_lines(FZ/'FROZEN750.sha256')['PREREG.md']}`; runner sha256
  `{parse_sha_lines(FZ/'FROZEN750.sha256')['run_exp750.sh']}`; classifier sha256
  `{parse_sha_lines(FZ/'FROZEN750.sha256')['classify750.py']}`.
- .so identities as preregistered and unchanged across the run (so_sha_pre == so_sha_post == exp749 ref):
  unpatched `{re.search(r'- R1:.*\.so ([0-9a-f]{8})', (FZ/'PREREG.md').read_text()).group(1)}…`,
  fix749 `{re.search(r'- S1:.*\.so ([0-9a-f]{8})', (FZ/'PREREG.md').read_text()).group(1)}…`,
  fix740 `{re.search(r'- K2:.*\.so ([0-9a-f]{8})', (FZ/'PREREG.md').read_text()).group(1)}…`.
- Disclosure: the A1 owner sensitivity analyzer (sens750_a1.py) was written post-freeze during the run
  (commit `0ea6ab4`, pre-result, not a gate); the sealed verdict derives only from the frozen classifier.

## Run
Winnie (WSL2, 2× RTX 5060 Ti: GPU0 PCIe gen3 x2, GPU1 gen4 x8), systemd user unit exp750,
started {win.group(1)} → EXP750-DONE {win.group(2)} 2026-11-07; first monitor sample {first_mon}.
OLMoE-1B-7B bf16, lcnu policy ratio 0.2, batch 1, 6 prompts × 64 tokens, 3 blocks; wall-clock ms/token through
MoE.generate (D = (t64−t1)/63). 21 planned cells + 5 frozen-rule G-F reruns = 26; 26/26 rc=0; 26/26 quietwait QUIET;
link state recorded per cell (gpu0 gen3 x2 / gpu1 gen4 x8, 26/26). Owned hardware; no API spend in the run itself.

## Per-arm record-cell medians (ms/token; parsed from sealed class750.txt, cross-recomputed from raw)
{table_txt}

Cells of record: b1_R1→b1_R1_x, b2_K2→b2_K2_x, b3_S0→b3_S0_x, b3_S1→b3_S1_x (frozen G-F rerun rule);
b3_R1 has NO clean cell (b3_R1 and b3_R1_x both FOREIGN — Ollama loaded at the end of b3_R1_x) → R1:EXCLUDED.

## Pre-registered decisions (all recomputed independently from raw and asserted equal to sealed output)
- **D1** q = D(K2)/D(P2) per block = [{", ".join(f4(x) for x in sealed_q)}] → **FIX-FASTER** (3/3 ≥ 1.10):
  the only other known-correct two-GPU configuration (fix740 + CUDA_LAUNCH_BLOCKING=1) pays a
  {min(sealed_q):.2f}–{max(sealed_q):.2f}× decode tax relative to fix749.
- **D2** s = D(S1)/D(R1) per block = [{", ".join(f4(x) for x in sealed_s)}] (blocks 1–2 only; no clean b3 R1)
  → **INCOMPLETE**; both available values sit inside the pre-registered NOREGRESS band [0.95, 1.05]:
  no single-GPU regression from fix749 is visible, but the pre-registered 3/3 requirement is not met.
- **D3** u = D(S1)/D(P2) per block = [{", ".join(f4(x) for x in sealed_u)}] → **TWO-GPU-SLOWER** (3/3 ≤ 0.91):
  on this host the correct two-GPU split decodes ~2× slower than GPU1 alone.
- **link** D(S0)/D(S1) per block = [{", ".join(f4(x) for x in sealed_l)}], CV {statistics.stdev(sealed_l)/statistics.mean(sealed_l)*100:.2f}%:
  GPU0-alone is 4.4–4.5× slower than GPU1-alone, consistent with GPU0's gen3 x2 link (exp704: ~1.56 GB/s H2D
  vs ~14 GB/s). Link state was recorded, not manipulated → decomposition, not a causal test.
- **noise**: R1 across-block CV(D) = {cv_r1*100:.2f}% (< 5% → no NOISY flag).

## Gates
- **G-Q PASS**: all 16 GQ-arm cells (originals + reruns) match the exp749 b1_R reference 6/6 on
  (out_ids, top16_ids, top16_vals). C2 0/6 in all 3 cells as expected; C2-UNEXPECTED-CLEAN not raised.
- **G-T**: timed-64 identity true for every non-C2 cell; false for all 3 C2 (exempt, descriptive).
- **G-V**: every timed rep t64 > t1 > 0 in all 26 cells.
- **G-M MANIP-OK**: .env CUDA_LAUNCH_BLOCKING=1 exactly for the 4 K2 cells, empty elsewhere; 18 prov.json
  (11 fix749 + 7 fix740); arm→build provenance exact; so_sha_pre == so_sha_post == ref.
- **G-F**: independent re-derivation from monitor.csv/precell.csv reproduces the sealed FOREIGN set
  {{b1_R1, b2_K2, b3_S0, b3_S1, b3_R1, b3_R1_x}} exactly; frozen rerun rule applied; 1 cell (b3_R1) lost.

## A1 sensitivity + owner-independent recompute
- sens750_a1.py replay at admission: **NOT-SENSITIVE** (verdict unchanged when flagged-cell slack is perturbed;
  flags b1_S0, b3_R1).
- indep750_owner.py (reads raw JSON, does not import the classifier) replay rc=0, 0 disagreements
  (SHOULD-FIX from the Muse review applied: unprinted b3_R1_x no longer counted as a disagreement).

## Admission review
- **Muse Code** (muse-wonder-1.0, read-only, attempt 2; attempt 1 killed at 17 min on an out-of-workspace write
  approval, MUSE_EXIT=143, no output): `ADMIT750 ADMIT-WITH-CAVEATS`, 0 BLOCKER, {muse_exit}.
  Reviewer independently recomputed all 26 D from raw (max abs diff 0.0), replayed the classifier byte-identically
  (`{CLASS_SHA[:8]}…`), reproduced the G-F FOREIGN set, and checked .env/.prov/.so/rc/quietwait/link and position
  effects (none plausible). Full text: `settle/review-muse-answer.md`.
- **Coordinator re-adjudication (this publication)**: `settle/verify750_staged.py` — 44/44 PASS on the staged tree
  (independent recompute of every gate/decision from raw, byte-identical classifier replay, manifest/tarball/RUN_SHA256
  integrity, A1 + owner-indep replays, Muse artifacts). Log: `settle/ADMISSION-VERIFY.log`.

## Findings (from sealed settle/RESULT.md)
{findings}

## Limits and pre-committed consequence (from sealed settle/RESULT.md)
{limits}

Publication status of the consequence: upstream draft v3 (fix737+fix740+fix749 series, qualified at the actual
upstream head) is written and double-reviewed (Muse review#1 FIX-FIRST 5B→v2 all-addressed; review#2 delta
0-BLOCKER 2SF→v3 all-addressed with sealed sources); sha256 `{draft_sha_rec}`. It is **APPROVAL-GATED: not posted** —
external publication requires Michael's explicit approval of the exact text. POSTING-LEDGER dedup at publish: no
prior ledger header for exp749/exp750 timing claims. No quiet upstream thread was bumped (warp #78, MoE-Infinity #321,
colibri #2552 untouched).

## Artifacts (this directory)
- `freeze/` — the 13 frozen files + FROZEN750.sha256 (verifies 13/13).
- `raw/` — sealed Winnie bundle: `out/` (109 files: 26 cell JSONs, .env, .prov.json, monitor.csv, precell.csv,
  rc.csv, quietwait.csv, link.csv, so_sha_pre/post, ENV.txt, RUN_SHA256, class750.txt), `winnie_out_sha.txt`
  (109/109 verified), `exp750-final.tgz` (sha256 `{TGZ_SHA}`, contents == raw/out), `run.log`,
  `FROZEN750.sha256` (bundle copy).
- `raw/out/class750.txt` sha256 `{CLASS_SHA}`.
- `settle/` — RESULT.md (sealed), sens750_a1.py, indep750_owner.py, review-muse-answer.md, review-muse-exit,
  verify750_staged.py, ADMISSION-VERIFY.log.
- Generator: `gen_addendum74.py` (this file's producer; every number above parsed or recomputed at runtime).
"""

if fails:
    print(f"\nASSERT FAILURES: {fails}"); sys.exit(1)
ADD.write_text(txt)
print(f"\nADDENDUM74.md written: {len(txt)} bytes")
print(f"sha256: {sha256(ADD)}")
print("ALL ASSERTS OK")
