#!/usr/bin/env python3
"""exp787 fixtures — analyzer self-tests. Run: python3 fixtures787.py <tmpdir>
7 cases; all must PASS (expected rc / expected fail-reason match)."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="fx787-")
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(os.path.join(tmp, "out"))
shutil.copy(os.path.join(HERE, "analyze787.py"), tmp)
shutil.copy(os.path.join(HERE, "cells787.json"), tmp)

ARMS = {"C": (["C25a", "C25b"], None),
        "W": (["W25a", "W25b"], "1,8,1,2;1,8,1,2"),
        "B": (["B25a", "B25b"], "1,2,4,4;1,1,8,2")}

def mkcell(cid, arm, mean, det_frac=1.0, sha_seed=0):
    cfg = ARMS[arm][1]
    rows = []
    for i in range(24):
        rows.append({"i": i, "n_new": 32, "decode_tok_s": round(mean * (1 + 0.05 * ((i % 5) - 2) / 5), 3),
                     "out_sha": f"{arm}{sha_seed}{i:02d}" if (i / 24) < det_frac else f"{arm}{sha_seed}X{i:02d}"})
    return {"id": cid, "rows": rows, "grouped_decode_effective": True,
            "unvalidated_hw_env": "1",
            "grouped_cfg_env": cfg if cfg else None}

def run(tag, cells, expect):
    for cid, arm, mean, kw in cells:
        json.dump(mkcell(cid, arm, mean, **kw), open(os.path.join(tmp, "out", cid + ".json"), "w"))
    r = subprocess.run([sys.executable, "analyze787.py", "."], cwd=tmp, capture_output=True, text=True)
    got = [l for l in r.stdout.splitlines() if l.startswith("EXP787")]
    ok = expect in (got[0] if got else "")
    det = [l for l in r.stdout.splitlines() if l.startswith("det[")]
    print(("PASS" if ok else "FAIL"), tag, "->", got[0] if got else r.stdout[:120], "|", det[0] if det else "")
    return ok

ok = True
ok &= run("fx1-major (W +4%)", [("C25a", "C", 10.0, {}), ("C25b", "C", 10.0, {}),
                                 ("W25a", "W", 10.4, {}), ("W25b", "W", 10.4, {}),
                                 ("B25a", "B", 10.05, {}), ("B25b", "B", 10.05, {})], "rc=1")
ok &= run("fx2-mild (B +2%)",  [("C25a", "C", 10.0, {}), ("C25b", "C", 10.0, {}),
                                 ("W25a", "W", 10.1, {}), ("W25b", "W", 10.1, {}),
                                 ("B25a", "B", 10.2, {}), ("B25b", "B", 10.2, {})], "rc=2")
ok &= run("fx3-nomove",        [("C25a", "C", 10.0, {}), ("C25b", "C", 10.0, {}),
                                 ("W25a", "W", 10.1, {}), ("W25b", "W", 10.1, {}),
                                 ("B25a", "B", 9.95, {}), ("B25b", "B", 9.95, {})], "rc=3")
ok &= run("fx4-regression-w-masks", [("C25a", "C", 10.0, {}), ("C25b", "C", 10.0, {}),
                                 ("W25a", "W", 9.0, {}), ("W25b", "W", 9.0, {}),
                                 ("B25a", "B", 9.9, {}), ("B25b", "B", 9.9, {})], "rc=3")
ok &= run("fx5-valid-then-break", [("C25a", "C", 10.0, {}), ("C25b", "C", 10.0, {}),
                                   ("W25a", "W", 10.4, {}), ("W25b", "W", 10.4, {}),
                                   ("B25a", "B", 10.05, {}), ("B25b", "B", 10.05, {})], "rc=1")
# fx5 sabotage: break banner on one cell after writing
p = os.path.join(tmp, "out", "W25b.json"); d = json.load(open(p)); d["grouped_decode_effective"] = False
json.dump(d, open(p, "w"))
r = subprocess.run([sys.executable, "analyze787.py", "."], cwd=tmp, capture_output=True, text=True)
line = [l for l in r.stdout.splitlines() if l.startswith("EXP787")][0]
print(("PASS" if "rc=9" in line else "FAIL"), "fx5-banner broken ->", line)
ok &= "rc=9" in line

ok &= run("fx6-valid-then-cfgbreak", [("C25a", "C", 10.0, {}), ("C25b", "C", 10.0, {}),
                                ("W25a", "W", 10.4, {}), ("W25b", "W", 10.4, {}),
                                ("B25a", "B", 10.4, {}), ("B25b", "B", 10.4, {})], "rc=1")
# fx6 sabotage: wrong cfg echo on B25b
p = os.path.join(tmp, "out", "B25b.json"); d = json.load(open(p)); d["grouped_cfg_env"] = "9,9,9,9;9,9,9,9"
json.dump(d, open(p, "w"))
r = subprocess.run([sys.executable, "analyze787.py", "."], cwd=tmp, capture_output=True, text=True)
line = [l for l in r.stdout.splitlines() if l.startswith("EXP787")][0]
print(("PASS" if "rc=9" in line else "FAIL"), "fx6-cfg mismatch ->", line)
ok &= "rc=9" in line

# fx7: det counts reported (W half-divergent) — verdict must stay rc from speed
ok &= run("fx7-det-descriptive", [("C25a", "C", 10.0, {"det_frac": 1.0, "sha_seed": 0}),
                                   ("C25b", "C", 10.0, {"det_frac": 1.0, "sha_seed": 0}),
                                   ("W25a", "W", 10.4, {"det_frac": 1.0, "sha_seed": 1}),
                                   ("W25b", "W", 10.4, {"det_frac": 0.5, "sha_seed": 1}),
                                   ("B25a", "B", 10.4, {"det_frac": 1.0, "sha_seed": 2}),
                                   ("B25b", "B", 10.4, {"det_frac": 1.0, "sha_seed": 2})], "rc=1")
print("ALL:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
