#!/usr/bin/env python3
"""Seal exp752 -> ADDENDUM75. Re-runs the frozen analyzer on raw/out and asserts every number quoted in the addendum.
Read-only w.r.t. raw/. Usage: python3 gen_addendum75.py  (from this directory)."""
import hashlib, json, os, re, subprocess, sys, tempfile, shutil

H = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(H, "raw")
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()

# 1. raw manifest integrity (sha256 computed on Winnie before pull; transfer re-verified both sides 55/55)
bad = 0
for line in open(os.path.join(RAW, "MANIFEST.sha256")):
    h, p = line.split(None, 1); p = p.strip()
    fp = os.path.join(RAW, p) if p == "run.log" else os.path.join(RAW, "out", p)
    if sha(fp) != h:
        bad += 1; print("MISMATCH", p)
assert bad == 0, "manifest mismatch"

# 2. executed runner == frozen runner; executed build == frozen patched build
art = {}
for l in open(os.path.join(H, "freeze", "ARTIFACT.sha256")):
    if "winnie" in l or "HEAD" in l:
        continue
    h, p = l.split(None, 1); art[p.strip().lstrip("./")] = h
rs = open(os.path.join(RAW, "out", "RUN_SHA256")).read()
checked = 0
for l in rs.strip().splitlines():
    h, p = l.split(None, 1); p = p.strip()
    if p in art:
        assert art[p] == h, f"RUN_SHA256 != freeze for {p}"
        checked += 1
assert checked >= 9, f"only {checked} runner files cross-checked"
assert "95da1b70b99fbec905c1e8ec6d8a90172d68fcbf69ccacc668adff9005fd20e1  src/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so" in rs
env = open(os.path.join(RAW, "out", "ENV.txt")).read()
assert "/home/mfeth/exp752/src/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so" in env, "private patched build not loaded"
assert "033798811664f5d89cae58049ff16e912ebc5862" in env, "base HEAD mismatch"

# 3. frozen analyzer re-run == sealed verdict (run from a temp copy so freeze stays untouched)
tmp = tempfile.mkdtemp()
try:
    shutil.copy(os.path.join(H, "freeze", "analyze752.py"), tmp)
    shutil.copy(os.path.join(H, "freeze", "cells.json"), tmp)
    out = subprocess.run([sys.executable, os.path.join(tmp, "analyze752.py"), os.path.join(RAW, "out")],
                         capture_output=True, text=True,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}).stdout
finally:
    shutil.rmtree(tmp)
sealed = open(os.path.join(RAW, "out", "verdict.txt")).read()
assert out == sealed, "re-run verdict differs from sealed verdict.txt"

def num(pat):
    m = re.search(pat, out); assert m, pat; return float(m.group(1))

# 4. verdict + arm numbers exactly as quoted
assert "VERDICT RETIRE:NO-CHANGE(PARITY-NA)|COMPL:FASTER(PARITY-NA)|TOTAL:FASTER(PARITY-NA)" in out
assert abs(num(r"arm H: \{'ms': ([\d.]+)") - 93.90) < 0.005
assert abs(num(r"arm R: \{'ms': ([\d.]+)") - 90.98) < 0.005
assert abs(num(r"arm RC: \{'ms': ([\d.]+)") - 85.70) < 0.005
assert abs(num(r"arm hf: \{'ms': ([\d.]+)") - 31.79) < 0.005
assert "'n': 2" in out.split("arm H:")[1].split("arm R:")[0] and "'n': 3" in out.split("arm R:")[1].split("arm RC:")[0]
# table busy/idle per arm
for a, b, i in (("hf", 14.15, 17.62), ("H", 38.37, 55.81), ("R", 41.28, 50.82), ("RC", 39.24, 47.59)):
    seg = out.split(f"arm {a}: ")[1].split("\n")[0]
    assert abs(float(re.search(r"'busy': ([\d.]+)", seg).group(1)) - b) < 0.005, a
    assert abs(float(re.search(r"'idle': ([\d.]+)", seg).group(1)) - i) < 0.005, a
assert abs(num(r"RETIRE R-H = (-?[\d.]+) ms/tok \(idle ([+-]?[\d.]+), busy ([+-]?[\d.]+)\)") - (-2.92)) < 0.005
assert abs(num(r"RETIRE R-H = -?[\d.]+ ms/tok \(idle (-?[\d.]+)") - (-4.99)) < 0.005
assert abs(num(r"RETIRE R-H = -?[\d.]+ ms/tok \(idle -?[\d.]+, busy ([+-]?[\d.]+)\)") - 2.91) < 0.005
assert abs(num(r"COMPL RC-R = (-?[\d.]+)") - (-5.28)) < 0.005
assert abs(num(r"TOTAL RC-H = (-?[\d.]+)") - (-8.20)) < 0.005
assert abs(num(r"TOTAL RC-H = -?[\d.]+ ms/tok \(idle (-?[\d.]+)") - (-8.22)) < 0.005
assert abs(num(r"GAP H-hf = ([\d.]+)") - 62.11) < 0.005
assert abs(num(r"closes ([\d.]+) of it") - 0.132) < 1e-3
assert "separated_fast=True separated_slow=False" in out.split("TOTAL")[1]
assert "COVARIATE foreign_other_gpu_max across clean cells: [0]" in out
assert out.count(" CLEAN") == 10 and "cell H_1" in out and "EXCLUDED:ci-runner-active;gpu-contamination" in out
assert "cell RC_1" in out and re.search(r"cell RC_1: .* EXCLUDED:ci-runner-active\n", out)

# 5. AMENDMENT1 coverage check: grouped_batches == 0 in every engine cell
cells = json.load(open(os.path.join(H, "freeze", "cells.json")))
for c in cells:
    if c["arm"] in ("H", "R", "RC"):
        d = json.load(open(os.path.join(RAW, "out", c["id"] + ".json")))
        g = sum((r.get("routing_delta") or {}).get("grouped_batches", 0) for r in d["rows"])
        assert g == 0, f"{c['id']} grouped_batches={g}"

# 6. parity facts: the only divergence in the whole matrix is contaminated H_1, prompt 5, token 31
ids = {}
for c in cells:
    d = json.load(open(os.path.join(RAW, "out", c["id"] + ".json")))
    ids[c["id"]] = [tuple(r["out_ids"]) for r in d["rows"]]
eng = [c["id"] for c in cells if c["arm"] in ("H", "R", "RC")]
ref = ids["H_2"]
for cid in eng:
    if cid == "H_1":
        continue
    assert ids[cid] == ref, f"{cid} differs from quiet-cell consensus"
t1, t2 = ids["H_1"][5], ref[5]
k = next(j for j in range(min(len(t1), len(t2))) if t1[j] != t2[j])
assert k == 31 and t1[31] == 0 and t2[31] == 14 and len(t1) == len(t2) == 64, (k, t1[31], t2[31])
hf5 = ids["hf_1"][5]
assert list(ref[5]) == list(hf5), "hf prompt5 does not match engine consensus"
# counters identical in H_1 (no routing failure accompanies the divergence)
for cid in ("H_1", "H_2"):
    rd = json.load(open(os.path.join(RAW, "out", cid + ".json")))["rows"][5]["routing_delta"]
    assert rd["route_failures"] == 0 and rd["stale_failures_quarantined"] == 0 and rd["route_batches"] == 1040

# 7. timeline as quoted
rl = open(os.path.join(RAW, "run.log")).read()
assert "== 2026-11-07T20:01:11Z start" in rl and "== 2026-11-07T23:51:31Z EXP752-DONE" in rl
assert re.search(r"21:31:44Z H_1 arm=H gpu=1 qw=5412 TIMEOUT la=3\.73 foreign_any=0", rl)
assert rl.count(" QUIET ") == 11 and rl.count(" TIMEOUT ") == 1
assert all(f"foreign_any=0" in l for l in rl.splitlines() if " gpu=1 qw=" in l)
# smoke (pre-freeze, disclosed) parity: H/R/RC identical on 2 prompts
for a in ("R", "RC"):
    s = json.load(open(os.path.join(H, "freeze", "smoke_pre", a + ".json")))
    h = json.load(open(os.path.join(H, "freeze", "smoke_pre", "H.json")))
    assert [r["out_sha"] for r in s["rows"]] == [r["out_sha"] for r in h["rows"]]

print("ALL ASSERTS OK")
