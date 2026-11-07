#!/usr/bin/env python3
"""Seal exp751 -> ADDENDUM73. Re-runs the AMENDMENT1-frozen analyzer on raw/out and asserts every number quoted in the addendum."""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

H = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(H, "raw")

# 1. raw manifest integrity (sha256 computed on the instance before pull)
bad = 0
for line in open(os.path.join(RAW, "MANIFEST.sha256")):
    h, p = line.split(None, 1); p = p.strip()
    if p.startswith(("out/", "diag/", "run.log", "run2.log", "chain.status", "setup.log", "setup.attempt1.log", "build.fail1.log")):
        fp = os.path.join(RAW, p)
        if hashlib.sha256(open(fp, "rb").read()).hexdigest() != h: bad += 1; print("MISMATCH", p)
assert bad == 0, "manifest mismatch"
art = dict((l.split()[1], l.split()[0]) for l in open(os.path.join(H, "freeze", "ARTIFACT.sha256")))
sha = lambda f: hashlib.sha256(open(f, "rb").read()).hexdigest()
a1 = dict((l.split()[1], l.split()[0]) for l in open(os.path.join(H, "amendment1", "AMENDMENT1.sha256")))
# analyzer = AMENDMENT1 version (adds cgroup-PSI exclusion, pre-data); cells = freeze
assert sha(os.path.join(H, "amendment1", "analyze.py")) == a1["analyze.py"] and sha(os.path.join(H, "freeze", "cells.json")) == art["cells.json"]

# 2. frozen analyzer (amendment1 copy is byte-identical to freeze analyze.py) re-run
tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
try:
    shutil.copy(os.path.join(H, "amendment1", "analyze.py"), tmp)
    shutil.copy(os.path.join(H, "freeze", "cells.json"), tmp)
    out = subprocess.run([sys.executable, os.path.join(tmp, "analyze.py"), os.path.join(RAW, "out")],
                         capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}).stdout
finally:
    shutil.rmtree(tmp)
sealed = open(os.path.join(RAW, "out", "verdict.txt")).read()
assert out == sealed, "re-run verdict differs from sealed verdict.txt"

def num(pat):
    m = re.search(pat, out); assert m, pat; return float(m.group(1))

assert "VERDICT HOSTFN:WSL-INFLATED|GAP:PARTIAL|ROUTE:OFF-FASTER" in out
assert out.count(" CLEAN") == 10 and "MISSING/FAILED" not in out
assert abs(num(r"native ([\d.]+) us vs WSL") - 108.5) < 0.05
assert abs(num(r"HOSTFN native/WSL = ([\d.]+)") - 0.208) < 1e-3
assert abs(num(r"kern_sync native/WSL = ([\d.]+)") - 0.593) < 1e-3
assert abs(num(r"x 109 us = ([\d.]+) ms/token") - 15.6) < 0.05
assert abs(num(r"GAP on-hf native = ([\d.]+)") - 38.47) < 0.005
assert abs(num(r"= idle ([\d.]+) \+ busy") - 29.73) < 0.005
assert abs(num(r"native/WSL gap = ([\d.]+)") - 0.640) < 1e-3
assert abs(num(r"on/hf ratio native ([\d.]+)") - 2.72) < 0.005
assert abs(num(r"ROUTE off-on native = (-?[\d.]+)") - (-6.75)) < 0.005
assert "engine token-id parity across engine cells: True" in out
assert re.search(r"level spin=6: \{'hs': 84\.99", out)
rs = open(os.path.join(RAW, "out", "RUN_SHA256")).read()
a4 = dict((l.split()[1], l.split()[0]) for l in open(os.path.join(H, "amendment4", "AMENDMENT4.sha256")))
assert a4["run_exp751.sh"] in rs, "executed runner != AMENDMENT4 runner"
assert "ENGINE_RATIO=0.60" in open(os.path.join(RAW, "out", "RUN_SHA256")).read()
env = open(os.path.join(RAW, "out", "ENV.txt")).read()
assert "NOT-WSL" in env and "RTX 5060 Ti" in env and "cgroup v1" in env
# diag (AMENDMENT4 evidence): 0.70/0.65 OOM, 0.60 fits
d = open(os.path.join(RAW, "diag", "info2.txt")).read()
assert "ratio=0.70 RC=1" in d and "ratio=0.65 RC=1" in d and "ratio=0.60 RC=0 peak=15242" in d
for c in ("q_on_1", "q_off_1", "q_off_2", "q_on_2"):
    assert "out of memory" in open(os.path.join(RAW, "out", "a3_oom", c + ".log")).read()
print("ALL ASSERTS OK")
