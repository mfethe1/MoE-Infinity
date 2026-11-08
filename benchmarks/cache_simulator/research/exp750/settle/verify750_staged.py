#!/usr/bin/env python3
"""exp750 coordinator-admission verification — STAGED-TREE variant (lane 79990 follow-up controller).

Runs against the published research/exp750/ layout (freeze/ raw/ settle/) instead of the
original ~/warp-work/exp750-* working dir. Independent of classify750.py: recomputes every
gate (G-Q, G-T, G-V, G-M, G-F) and decision (D1/D2/D3, link, noise) from raw JSON/CSV,
cross-checks the sealed classifier output, replays it byte-exact, and verifies
provenance/manifest/tarball. Reference shas are PARSED AT RUNTIME from machine-recorded
files (RUN_SHA256, RESULT.md elided forms, Muse answer) — never hand-transcribed.
All checks print PASS/FAIL with evidence. Exit 0 only if every check passes.
"""
import hashlib, json, re, statistics, subprocess, sys, tarfile, tempfile
from pathlib import Path

R = Path(__file__).resolve().parent.parent     # research/exp750
OUT = R / "raw/out"
FZ = R / "freeze"
ST = R / "settle"
REF = json.load(open(FZ / "ref/exp749_b1_R.json"))
CELLS = json.load(open(FZ / "cells750.json"))
RESULT_TXT = (ST / "RESULT.md").read_text()
MUSE_ANS = (ST / "review-muse-answer.md").read_text()
CLS_TXT = (OUT / "class750.txt").read_text()

SEALED_VERDICT = ("VERDICT750 FIX-FASTER|INCOMPLETE|TWO-GPU-SLOWER|PASS|MANIP-OK "
                  "flags: R1:EXCLUDED(b3_R1:FOREIGN)")

fails = []
def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)

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

# ---------- runtime-parsed reference shas (no hand transcription) ----------
run_sha = parse_sha_lines(OUT / "RUN_SHA256")
frozen_list = parse_sha_lines(FZ / "FROZEN750.sha256")
FROZEN_SHA = run_sha.get("FROZEN750.sha256")          # recorded by Winnie runner
tgz_m = re.search(r"exp750-final\.tgz sha256 ([0-9a-f]{8})…([0-9a-f]{4})", RESULT_TXT)
muse_shas = set(re.findall(r"\b[0-9a-f]{64}\b", MUSE_ANS))
so_pre = {}
for arm in ("R1", "S1", "K2"):
    m = re.search(rf"- {arm}:.*\.so ([0-9a-f]{{8}})", (FZ / "PREREG.md").read_text())
    so_pre[arm] = m.group(1) if m else None

# ---------- A. integrity ----------
check("A0 reference shas parsed at runtime (RUN_SHA256/RESULT/Muse/PREREG)",
      bool(FROZEN_SHA) and bool(tgz_m) and bool(muse_shas) and all(so_pre.values()),
      f"frozen={str(FROZEN_SHA)[:8]}… tgz={tgz_m.group(1) if tgz_m else None}… "
      f"muse64s={len(muse_shas)} so={so_pre}")
check("A1 tarball sha256 matches RESULT-recorded elided form (prefix…suffix)",
      sha256(R / "raw/exp750-final.tgz").startswith(tgz_m.group(1))
      and sha256(R / "raw/exp750-final.tgz").endswith(tgz_m.group(2)),
      sha256(R / "raw/exp750-final.tgz")[:16] + "…")
check("A2 sealed class750.txt sha256 is among the 64-hex shas in the Muse answer",
      sha256(OUT / "class750.txt") in muse_shas, sha256(OUT / "class750.txt")[:16] + "…")
check("A3 FROZEN750.sha256 hashes to the value recorded in Winnie RUN_SHA256",
      sha256(FZ / "FROZEN750.sha256") == FROZEN_SHA)
rc = subprocess.run(["shasum", "-a", "256", "-c", "FROZEN750.sha256"], cwd=FZ,
                    capture_output=True, text=True)
oks = rc.stdout.count(": OK")
check("A4 staged freeze 13 files shasum -c", rc.returncode == 0 and oks == 13, f"{oks}/13 OK")

manifest = parse_sha_lines(R / "raw/winnie_out_sha.txt")
mm = [n for n, h in manifest.items() if not (OUT / n).exists() or sha256(OUT / n) != h]
check("A5 staged raw/out matches Winnie manifest", not mm,
      f"{len(manifest)-len(mm)}/{len(manifest)} match" + (f"; bad={mm[:5]}" if mm else ""))

with tempfile.TemporaryDirectory() as td:
    with tarfile.open(R / "raw/exp750-final.tgz") as tf:
        tf.extractall(td)
    tfiles = sorted(str(p.relative_to(td)) for p in Path(td).rglob("*") if p.is_file())
    t_out = [f for f in tfiles if "/out/" in f or f.startswith("out/")]
    bad = sum(1 for rel in t_out
              if not (OUT / rel.split("out/", 1)[1]).exists()
              or sha256(Path(td) / rel) != sha256(OUT / rel.split("out/", 1)[1]))
    check("A6 tarball out/ == staged raw/out", t_out and bad == 0,
          f"{len(t_out)} files in tarball out/, {bad} mismatched")

frozen = frozen_list
overlap = set(run_sha) & set(frozen)
mism = [n for n in overlap if run_sha[n] != frozen[n]]
check("A7 RUN_SHA256 vs FROZEN750: 12 overlapping match, lists FROZEN itself, omits tests/",
      len(overlap) == 12 and not mism and "FROZEN750.sha256" in run_sha
      and "tests/test_classify750.py" not in run_sha,
      f"overlap={len(overlap)} mismatch={len(mism)}")

pre = (OUT / "so_sha_pre.txt").read_text()
post = (OUT / "so_sha_post.txt").read_text()
refso = (FZ / "ref/exp749_so_sha_post.txt").read_text()
check("A8 so_sha_pre == so_sha_post == exp749 ref", pre == post == refso)
so_vals = dict((l.split("  ")[1].strip(), l.split("  ")[0]) for l in refso.splitlines() if l.strip())
check("A9 three .so identities match PREREG-recorded prefixes",
      any(k.endswith("/moei-engine/MoE-Infinity/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so")
          and v.startswith(so_pre["R1"]) for k, v in so_vals.items())
      and any("/moei-fix740/" in k and v.startswith(so_pre["K2"]) for k, v in so_vals.items())
      and any("/moei-fix749/" in k and v.startswith(so_pre["S1"]) for k, v in so_vals.items()),
      str(so_pre))

rcs = [l.split(",") for l in (OUT / "rc.csv").read_text().splitlines() if l.strip()]
check("A10 rc.csv 26/26 rc=0", len(rcs) == 26 and all(r[1].strip() == "0" for r in rcs), f"{len(rcs)} rows")
qw = [l for l in (OUT / "quietwait.csv").read_text().splitlines() if l.strip()]
check("A11 quietwait 26/26 QUIET", len(qw) == 26 and all("QUIET" in l for l in qw))
lk = [l for l in (OUT / "link.csv").read_text().splitlines() if l.strip()]
check("A12 link.csv 26 rows gpu0 gen3 x2 / gpu1 gen4 x8",
      len(lk) == 26 and all(re.search(r"0,\s*3,\s*2;1,\s*4,\s*8", l) for l in lk))

# ---------- B. sealed classifier replay ----------
proc = subprocess.run([sys.executable, str(FZ / "classify750.py"), str(OUT),
                       str(FZ / "ref/exp749_b1_R.json")],
                      cwd=FZ, capture_output=True, text=True)
body_norc = CLS_TXT[: -len("classify750 rc=0\n")] if CLS_TXT.endswith("classify750 rc=0\n") else CLS_TXT
check("B1 frozen classifier replay rc=0", proc.returncode == 0, proc.stderr[-200:] if proc.stderr else "")
check("B2 replay byte-identical to sealed class750.txt (runner-appended rc line accounted)",
      proc.stdout == CLS_TXT or proc.stdout == body_norc,
      f"exact={proc.stdout == CLS_TXT} minus-rc-line={proc.stdout == body_norc}")
check("B3 replayed stdout sha256",
      hashlib.sha256(proc.stdout.encode()).hexdigest()
      in (sha256(OUT / "class750.txt"), hashlib.sha256(body_norc.encode()).hexdigest()))

# ---------- C. independent recompute from raw ----------
def load_cell(cid):
    return json.load(open(OUT / f"{cid}.json"))

cell_ids = [c["id"] for c in CELLS]
x_ids = [cid + "_x" for cid in cell_ids if (OUT / f"{cid}_x.json").exists()]
all_ids = cell_ids + x_ids
check("C0 21 planned cells + 5 reruns = 26", len(cell_ids) == 21 and len(x_ids) == 5,
      f"{len(cell_ids)}+{len(x_ids)}")

cells_meta = {c["id"]: c for c in CELLS}
for x in x_ids:
    cells_meta[x] = dict(cells_meta[x[:-2]], id=x)
myD, myE, qmatch, tid_ok, gv_ok = {}, {}, {}, {}, {}
for cid in all_ids:
    d = load_cell(cid)
    rows = d["rows"]
    dps, eps = [], []
    t_ok, v_ok = True, True
    for r in rows:
        t64s, t1s, o64 = [], [], []
        for rep in r["timed"]:
            t1s.append(rep["t1_s"]); t64s.append(rep["t64_s"]); o64.append(rep["out_ids_64"])
            if not (rep["t64_s"] > rep["t1_s"] > 0):
                v_ok = False
        dps.append(statistics.median([(a - b) * 1000.0 / 63 for a, b in zip(t64s, t1s)]))
        eps.append(statistics.median([a * 1000.0 / 64 for a in t64s]))
        if any(o != r["out_ids"] for o in o64):
            t_ok = False
    myD[cid] = statistics.median(dps)
    myE[cid] = statistics.median(eps)
    n = 0
    for r, rr in zip(rows, REF["rows"]):
        if (r["out_ids"], r["top16_ids"], r["top16_vals"]) == (rr["out_ids"], rr["top16_ids"], rr["top16_vals"]):
            n += 1
    qmatch[cid] = n
    tid_ok[cid], gv_ok[cid] = t_ok, v_ok

check("C1 G-V timer sanity: every rep t64 > t1 > 0 in all 26 cells", all(gv_ok.values()))
gq_arms = ("R1", "S1", "S0", "P2", "K2")
gq_cells = [c for c in all_ids if cells_meta[c]["arm"] in gq_arms]
c2_cells = [c for c in all_ids if cells_meta[c]["arm"] == "C2"]
check("C2 G-Q strict (A2): all 16 GQ-arm cells (orig+_x) 6/6 vs exp749 b1_R",
      all(qmatch[c] == 6 for c in gq_cells),
      f"{len(gq_cells)} cells; counts={sorted(set(qmatch[c] for c in gq_cells))}")
check("C3 C2 0/6 in all cells (expected corrupt); C2-UNEXPECTED-CLEAN not raised",
      all(qmatch[c] == 0 for c in c2_cells) and "C2-UNEXPECTED-CLEAN" not in CLS_TXT)
check("C4 G-T timed identity: true for every non-C2 cell; false for all 3 C2",
      all(tid_ok[c] for c in all_ids if c not in c2_cells) and not any(tid_ok[c] for c in c2_cells))

k2 = [c for c in all_ids if cells_meta[c]["arm"] == "K2"]
gm_ok, gm_detail = True, []
for cid in all_ids:
    env = (OUT / f"{cid}.env").read_text()
    m = re.search(r"^CUDA_LAUNCH_BLOCKING=(.*)$", env, re.M)
    val = m.group(1).strip() if m else None
    want = "1" if cid in k2 else ""
    if val != want:
        gm_ok = False; gm_detail.append(f"{cid}:CLB={val!r}")
check("C5 G-M .env CLB=1 exactly for 4 K2 cells, empty elsewhere", gm_ok, "; ".join(gm_detail[:5]))
check("C6 K2 cell count == 4", len(k2) == 4, str(k2))

prov_ok, prov_bad = True, []
for cid in all_ids:
    arm = cells_meta[cid]["arm"]
    pj = OUT / f"{cid}.json.prov.json"
    if arm in ("S1", "S0", "P2"):
        so = json.load(open(pj))["store_so"] if pj.exists() else load_cell(cid).get("store_so", "")
        if "/moei-fix749/" not in so: prov_ok = False; prov_bad.append(f"{cid}:{so}")
    elif arm in ("K2", "C2"):
        so = json.load(open(pj))["store_so"] if pj.exists() else load_cell(cid).get("store_so", "")
        if "/moei-fix740/" not in so: prov_ok = False; prov_bad.append(f"{cid}:{so}")
    elif arm == "R1":
        so = load_cell(cid).get("store_so", "")
        if "/moei-engine/" not in so: prov_ok = False; prov_bad.append(f"{cid}:{so}")
check("C7 G-M provenance: fix749 arms->/moei-fix749/, fix740 arms->/moei-fix740/, R1->/moei-engine/",
      prov_ok, "; ".join(prov_bad[:5]))
nprov = len(list(OUT.glob("*.prov.json")))
check("C8 18 prov.json files (11 fix749 + 7 fix740)", nprov == 18, str(nprov))

def parse_mem(mid):
    mem = {}
    for chunk in mid.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        g, _, v = chunk.partition(",")
        mem[int(g.strip())] = float(v.strip())
    return mem

mon_rows = {}
for line in (OUT / "monitor.csv").read_text().splitlines():
    if not line.strip():
        continue
    parts = line.split(",")
    ts, cid = parts[0], parts[1]
    ollama = int(parts[-1])
    mem = parse_mem(",".join(parts[2:-1]))
    mon_rows.setdefault(cid, []).append((mem, ollama))
pre_mem = {}
for line in (OUT / "precell.csv").read_text().splitlines():
    if not line.strip():
        continue
    parts = line.split(",")
    pre_mem[parts[0]] = parse_mem(",".join(parts[1:-1]))

foreign = set()
for cid in all_ids:
    assigned = {int(g) for g in str(cells_meta[cid]["gpus"]).split(",")}
    rows = mon_rows.get(cid, [])
    if not rows:
        foreign.add(cid); continue
    base = pre_mem.get(cid, {})
    for mem, oll in rows:
        if oll >= 1:
            foreign.add(cid); break
        for g, v in mem.items():
            if g not in assigned and v > base.get(g, 0.0) + 512:
                foreign.add(cid); break
        if cid in foreign:
            break

sealed_foreign = set(re.findall(r"^(\w+): present=True .*? foreign=FOREIGN", CLS_TXT, re.M))
for m in re.finditer(r"^(\w+): present=True .*? foreign=FOREIGN .*? x: present=True clean=(\w+)", CLS_TXT, re.M):
    if m.group(2) == "False":
        sealed_foreign.add(m.group(1) + "_x")
check("C9 G-F independent FOREIGN set == sealed classifier set",
      foreign == sealed_foreign, f"mine={sorted(foreign)} sealed={sorted(sealed_foreign)}")
check("C10 FOREIGN set == {b1_R1,b2_K2,b3_S0,b3_S1,b3_R1,b3_R1_x}",
      foreign == {"b1_R1", "b2_K2", "b3_S0", "b3_S1", "b3_R1", "b3_R1_x"}, str(sorted(foreign)))

proc2 = subprocess.run([sys.executable, str(FZ / "classify750.py"), str(OUT), "--list-reruns"],
                       cwd=FZ, capture_output=True, text=True)
reruns = [l.strip() for l in proc2.stdout.splitlines() if l.strip()]
check("C11 --list-reruns == 5 FOREIGN originals", proc2.returncode == 0 and
      sorted(reruns) == sorted(["b1_R1", "b2_K2", "b3_S0", "b3_S1", "b3_R1"]), str(sorted(reruns)))

def clean(cid):
    if cid in foreign or not gv_ok[cid]:
        return False
    arm = cells_meta[cid]["arm"]
    if arm in gq_arms and qmatch[cid] != 6:
        return False
    if arm != "C2" and not tid_ok[cid]:
        return False
    return True

record = {}
for cid in cell_ids:
    x = cid + "_x"
    if clean(cid):
        record[cid] = cid
    elif x in all_ids and clean(x):
        record[cid] = x
    else:
        record[cid] = None
check("C12 cells of record: 4 replacements, b3_R1 has no clean cell",
      record["b1_R1"] == "b1_R1_x" and record["b2_K2"] == "b2_K2_x"
      and record["b3_S0"] == "b3_S0_x" and record["b3_S1"] == "b3_S1_x"
      and record["b3_R1"] is None
      and sum(1 for v in record.values() if v is None) == 1)

sealedD = {m.group(1): float(m.group(2)) for m in re.finditer(r"^(\w+): present=True .*? D=([0-9.]+)", CLS_TXT, re.M)}
for m in re.finditer(r"REPLACED-BY (\w+) \(D=([0-9.]+)\)", CLS_TXT):
    sealedD[m.group(1)] = float(m.group(2))
maxdiff = max(abs(myD[c] - sealedD[c]) for c in sealedD)
check("C13 my D == classifier-printed D for all 25 printed cells (max|diff| < 1e-9)",
      len(sealedD) == 25 and maxdiff < 1e-9, f"n={len(sealedD)} maxdiff={maxdiff:.3g}")
b3x_m = re.search(r"b3_R1_x is not printed by the classifier \(its\s+own D = ([0-9.]+)", RESULT_TXT)
check("C14 b3_R1_x not in sealed printout; my D matches RESULT-disclosed value",
      "b3_R1_x" not in {m.group(1) for m in re.finditer(r"^(\w+): present=True", CLS_TXT, re.M)}
      and b3x_m is not None and abs(myD["b3_R1_x"] - float(b3x_m.group(1))) < 0.01,
      f"D={myD['b3_R1_x']:.4f} RESULT={b3x_m.group(1) if b3x_m else None}")

def rec_D(block, arm):
    for cid, r in record.items():
        if r and cells_meta[cid]["block"] == block and cells_meta[cid]["arm"] == arm:
            return myD[r]
    return None

q = [(rec_D(b, "K2") / rec_D(b, "P2")) if rec_D(b, "K2") and rec_D(b, "P2") else None for b in (1, 2, 3)]
s = [(rec_D(b, "S1") / rec_D(b, "R1")) if rec_D(b, "S1") and rec_D(b, "R1") else None for b in (1, 2, 3)]
u = [(rec_D(b, "S1") / rec_D(b, "P2")) if rec_D(b, "S1") and rec_D(b, "P2") else None for b in (1, 2, 3)]
link = [(rec_D(b, "S0") / rec_D(b, "S1")) if rec_D(b, "S0") and rec_D(b, "S1") else None for b in (1, 2, 3)]

sealed_q = [float(x) for x in re.search(r"D1 q=D\(K2\)/D\(P2\) per block: \[([^\]]+)\]", CLS_TXT).group(1).split(",")]
sealed_s = [float(x) for x in re.search(r"D2 s=D\(S1\)/D\(R1\) per block: \[([^\]]+)\]", CLS_TXT).group(1).split(",")]
sealed_u = [float(x) for x in re.search(r"D3 u=D\(S1\)/D\(P2\) per block: \[([^\]]+)\]", CLS_TXT).group(1).split(",")]
sealed_l = [float(x) for x in re.search(r"link ratio D\(S0\)/D\(S1\) per block: \[([^\]]+)\]", CLS_TXT).group(1).split(",")]
check("C15 D1 ratios match sealed", all(a is not None and abs(a - b) < 1e-12 for a, b in zip(q, sealed_q)) and len(q) == 3, str([round(x, 4) for x in q]))
check("C16 D2 ratios match sealed (block3 missing)", all(abs(a - b) < 1e-12 for a, b in zip([x for x in s if x is not None], sealed_s)), str(s))
check("C17 D3 ratios match sealed", all(abs(a - b) < 1e-12 for a, b in zip(u, sealed_u)), str([round(x, 4) for x in u]))
check("C18 link ratios match sealed", all(a is not None and abs(a - b) < 1e-12 for a, b in zip(link, sealed_l)), str([round(x, 3) for x in link]))

d1 = "FIX-FASTER" if all(x >= 1.10 for x in q) else ("WORKAROUND-FASTER" if all(x <= 0.91 for x in q) else ("EQUIVALENT" if all(0.95 <= x <= 1.05 for x in q) else "MIXED"))
avail_s = [x for x in s if x is not None]
if len(avail_s) < 3: d2 = "INCOMPLETE"
else: d2 = "NOREGRESS-T" if all(0.95 <= x <= 1.05 for x in s) else ("REGRESS-T" if all(x > 1.05 for x in s) else ("FASTER-T" if all(x < 0.95 for x in s) else "UNRESOLVED-T"))
d3 = "TWO-GPU-FASTER" if all(x >= 1.10 for x in u) else ("TWO-GPU-SLOWER" if all(x <= 0.91 for x in u) else "NEUTRAL/MIXED")
r1d = [x for x in (rec_D(b, "R1") for b in (1, 2, 3)) if x is not None]
cv = statistics.stdev(r1d) / statistics.mean(r1d)
noisy = cv > 0.05
gq_summary = "PASS" if all(qmatch[c] == 6 for c in gq_cells) else "FAIL"
check("C19 D1 verdict FIX-FASTER (all q >= 1.10)", d1 == "FIX-FASTER", f"q={[round(x, 3) for x in q]}")
check("C20 D2 verdict INCOMPLETE (no clean b3 R1; both available in NOREGRESS band)",
      d2 == "INCOMPLETE" and all(0.95 <= x <= 1.05 for x in avail_s), f"s={[round(x, 3) for x in avail_s]}")
check("C21 D3 verdict TWO-GPU-SLOWER (all u <= 0.91)", d3 == "TWO-GPU-SLOWER", f"u={[round(x, 4) for x in u]}")
check("C22 noise: R1 across-block CV < 5% -> no NOISY flag", not noisy, f"CV={cv*100:.2f}%")
flags = "R1:EXCLUDED(b3_R1:FOREIGN)"
my_verdict = f"VERDICT750 {d1}|{d2}|{d3}|{gq_summary}|MANIP-OK flags: {flags}"
check("C23 my independently derived verdict == sealed verdict", my_verdict == SEALED_VERDICT, my_verdict)
check("C24 sealed verdict present in class750.txt and RESULT.md",
      SEALED_VERDICT in CLS_TXT and SEALED_VERDICT in RESULT_TXT)

# ---------- D. A1 + owner indep replays ----------
with tempfile.TemporaryDirectory() as td:
    import shutil
    shutil.copy(ST / "sens750_a1.py", Path(td) / "sens750_a1.py")
    shutil.copy(FZ / "classify750.py", Path(td) / "classify750.py")
    p3 = subprocess.run([sys.executable, str(Path(td) / "sens750_a1.py"), str(OUT),
                         str(FZ / "ref/exp749_b1_R.json"), "--cells", str(FZ / "cells750.json")],
                        cwd=td, capture_output=True, text=True)
check("D1 sens750_a1 replay rc=0, flags b1_S0+b3_R1, NOT-SENSITIVE",
      p3.returncode == 0 and "A1 RESULT: NOT-SENSITIVE" in p3.stdout
      and "b1_S0" in p3.stdout and "b3_R1" in p3.stdout, p3.stdout.strip()[-160:])
p4 = subprocess.run([sys.executable, str(ST / "indep750_owner.py"), str(OUT),
                     str(FZ / "ref/exp749_b1_R.json")], cwd=ST, capture_output=True, text=True)
check("D2 indep750_owner replay rc=0 (SHOULD-FIX applied)", p4.returncode == 0,
      (p4.stdout.strip()[-120:] or p4.stderr.strip()[-120:]))

# ---------- E. Muse admission review ----------
check("E1 Muse answer: ADMIT750 ADMIT-WITH-CAVEATS, 0 BLOCKER, MUSE_EXIT=0",
      MUSE_ANS.rstrip().endswith("ADMIT750 ADMIT-WITH-CAVEATS") and "BLOCKER: none" in MUSE_ANS
      and (ST / "review-muse-exit").read_text().strip().startswith("MUSE_EXIT=0"),
      (ST / "review-muse-exit").read_text().strip())

print()
print(f"RESULT: {'ALL PASS' if not fails else 'FAILURES: ' + str(fails)}  ({len(fails)} failed)")
sys.exit(0 if not fails else 1)
