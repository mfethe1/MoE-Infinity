#!/usr/bin/env python3
"""exp785 analyzer fixtures. Builds synthetic out/ trees and asserts analyze785.py verdicts.
Cases: clean-regression (rc4), major-pos (rc1), mild-pos (rc2), no-move (rc3),
nondet (rc9), missing-cell (rc9)."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

def row(i, tps, sha):
    return {"i": i, "n_in": 9, "n_new": 32, "t_1tok_s": 0.1, "t_full_s": 0.1 + 32.0 / tps,
            "decode_tok_s": tps, "out_sha": sha, "out_ids": [i] * 32,
            "stats_delta": {"policy_routed_hits": 900, "policy_routed_misses": 100},
            "routing_delta": {}}

def cell(cid, tps, sha=None, n=24):
    # default sha keyed by CONFIG (cid[:3]) + row: greedy decode => reps a/b identical
    cfg = cid[:3]
    return {"policy": "lcnu", "ratio": 0.75 if "75" in cid else 0.25, "rows":
            [row(i, tps, sha if sha else f"{cfg}-{i}") for i in range(n)],
            "spec_prefetch_effective": cid.startswith("S"),
            "threads_effective": 4, "gpu_route_effective": True}

IDS = ["C75a","S75a","C25a","S25a","C75b","S75b","C25b","S25b"]

def build(root, tps_map, sha_fn=None):
    os.makedirs(os.path.join(root, "out"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "cells785.json"), os.path.join(root, "cells785.json"))
    for cid in IDS:
        if tps_map.get(cid) is None:
            continue  # omit -> missing cell
        c = cell(cid, tps_map[cid], sha_fn(cid) if sha_fn else None)
        json.dump(c, open(os.path.join(root, "out", cid + ".json"), "w"))

def verdict(root):
    r = subprocess.run([sys.executable, os.path.join(HERE, "analyze785.py"), root],
                       capture_output=True, text=True)
    first = (r.stdout.strip().splitlines() or ["rc=?"])[0]
    return first, r.stdout

def case(name, tps_map, expect_rc, sha_fn=None):
    root = tempfile.mkdtemp(prefix="fx785-")
    try:
        build(root, tps_map, sha_fn)
        head, full = verdict(root)
        ok = f"rc={expect_rc}" in head
        print(("PASS" if ok else "FAIL"), name, "->", head)
        if not ok:
            print(full)
            return False
        return True
    finally:
        shutil.rmtree(root, ignore_errors=True)

ok = True

def m(c75, s75, c25, s25):
    d = {}
    for cid in IDS:
        key = cid[:3]
        d[cid] = {"C75": c75, "S75": s75, "C25": c25, "S25": s25}[key]
    return d

root_all = tempfile.mkdtemp(prefix="fx785-")
try:
    # 1) regression
    ok &= case("regression-rc4", m(10.4, 4.2, 10.1, 4.5), 4)
    # 2) major pos
    ok &= case("major-pos-rc1", m(10.0, 16.0, 10.0, 16.0), 1)
    # 3) mild pos (>= +10%)
    ok &= case("mild-pos-rc2", m(10.0, 11.2, 10.0, 11.4), 2)
    # 4) no move
    ok &= case("no-move-rc3", m(10.0, 10.02, 10.0, 9.98), 3)
    # 5) nondet in S75 only
    def sha_nondet(cid):
        return None if not cid.startswith("S75") else (cid + "-X" if cid.endswith("b") else cid + "-Y")
    # same tps -> rc9 via nondet
    ok &= case("nondet-rc9", m(10.0, 4.0, 10.0, 4.0), 9, sha_fn=lambda cid: None if not cid.startswith("S75") else (cid + "x" if cid.endswith("b") else cid + "y"))
    # 6) missing cell
    mm = m(10.4, 4.2, 10.1, 4.5); mm["S25b"] = None
    ok &= case("missing-cell-rc9", mm, 9)
finally:
    shutil.rmtree(root_all, ignore_errors=True)

print("FIXTURES785", "ALL-PASS" if ok else "FAILURES")
sys.exit(0 if ok else 1)
