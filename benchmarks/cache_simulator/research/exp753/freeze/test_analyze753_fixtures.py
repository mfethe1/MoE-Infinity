#!/usr/bin/env python3
"""exp753 analyzer fixtures — synthetic unit tests (NOT measurement data, NOT
model results; these are exercised on macOS and assert the analyzer's decision
wiring only). Scenarios bite each fixed defect:
  A          correct golden path + exact stage pairing (monotone R9), trace spans,
             prompt-4 frozen-prefix, wait/residual chain (R4/#10), nested
             graph-probe steps (R2), production .trace.jsonl naming (R1)
  B          n_new/len != 64 rows excluded + INVALID-ROW-NNEW (R10)
  C          engine p4 21-ID prefix ACCEPTED (regression)
  D-failfast failed cells excluded from parity (SUB-2 #5/#12)
  E-env      graph positive-control FAIL -> INCONCLUSIVE-ENV
  F-p4prefix corrupted engine p4 -> PARITY-FAIL (SUB-2 #1)
  G-tf32     allow_tf32=True -> MANIP flag (R6)
  H-badsyntax unparsable site enum -> MANIP flag + no crash (R11)
  K-kerncov  tracer drops kernels -> KERN-COVERAGE (SUB-2 #6)
  M-rowschema malformed row -> ROW-SCHEMA flag, never KeyError (R14)
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SI = {"SETINPUTS_ENTER": 1, "SETINPUTS_EXIT": 2, "DISPATCH_ENTER": 3, "DISPATCH_HF_LAUNCH": 4,
      "ROUTE_CB_ENTER": 5, "ROUTE_CB_PUSH": 6, "ROUTE_FUNC_POP": 7, "RF_ENQ": 8,
      "ROUTE_FUNC_DONE": 9, "EXEC_PUSH": 10, "EXEC_POP": 11, "EXEC_FWD_ENTER": 12,
      "EXEC_FWD_RETURN": 13, "OUTPUT_DONE": 14, "KERN": 15, "COMPLETE_ZERO": 16,
      "WAIT_ENTER": 17, "WAIT_CV_WAKE": 18, "WAIT_EXIT": 19, "COMPLETION_CB": 20, "RETCB": 21}


def gen(cid, tpfx, drop_kern_k=None):
    """One cell trace: 6 prompt windows x 16 decode gens x 8 experts.
    Windows 1e9-2e9, 3e9-4e9, ... 11e9-12e9; gens 100..115 (no reset)."""
    recs = []
    for w in range(6):
        t0 = (2 * w + 1) * int(1e9)
        for g in range(100, 116):
            t = t0 + (g - 100) * int(1e6)
            def ev(off, site, pay=0):
                recs.append((t + off, site, pay, g))
            ev(500, SI["SETINPUTS_ENTER"]); ev(550, SI["SETINPUTS_EXIT"])
            ev(1000, SI["DISPATCH_ENTER"]); ev(2000, SI["DISPATCH_HF_LAUNCH"])
            ev(3000, SI["ROUTE_CB_ENTER"]); ev(5000, SI["ROUTE_CB_ENTER"])
            ev(6000, SI["ROUTE_CB_PUSH"])
            ev(7000, SI["ROUTE_FUNC_POP"]); ev(8000, SI["ROUTE_FUNC_DONE"])
            ev(12000, SI["WAIT_ENTER"])
            for k in range(8):
                ev(9000 + k, SI["RF_ENQ"])
                ev(10000 + k, SI["EXEC_PUSH"], 1 if k % 2 == 0 else 2)
                ev(11000 + k, SI["EXEC_POP"], 1 if k % 2 == 0 else 2)
                ev(15000 + k, SI["EXEC_FWD_RETURN"])
                ev(16000 + k, SI["OUTPUT_DONE"])
                if not (drop_kern_k is not None and k >= drop_kern_k):
                    ev(17000 + k, SI["KERN"], 500000)  # 0.5ms sample each
            ev(12400, SI["COMPLETION_CB"])           # cb-then-exit (inside wait)
            ev(12500, SI["WAIT_CV_WAKE"])
            ev(12900, SI["WAIT_EXIT"])
            ev(16500, SI["OUTPUT_DONE"])
            ev(18000, SI["COMPLETE_ZERO"])
            ev(20000, SI["RETCB"])
    with open(os.path.join(tpfx, cid + ".trace.jsonl"), "w") as f:  # R1 production naming
        f.write(json.dumps({"format": "exp753-trace-v1", "records": len(recs), "dropped": 0}) + "\n")
        for (t, s, p, g) in recs:
            f.write(json.dumps({"ns": t, "s": s, "e": p, "g": g}) + "\n")


def cell(out, cid, med_t, tf=1.0, n_new=64, tf32=False, no_outids=False):
    rows = []
    for i in range(6):
        row = {"i": i, "win_mono": [(2 * i + 1) * int(1e9), (2 * i + 1) * int(1e9) + 15_100_000],
               "t_1tok_s": 10.0, "t_full_s": 10.0 + med_t * 63 / 1000 * tf, "n_new": n_new,
               "out_ids": [5, 6, 7] + [330] * (n_new - 3) if not no_outids else None}
        if no_outids:
            del row["out_ids"]
        rows.append(row)
    r = {"arm": cid.split("_")[0], "rows": rows,
         "allow_tf32": {"matmul": bool(tf32), "cudnn": bool(tf32)}}
    json.dump(r, open(os.path.join(out, cid + ".json"), "w"))
    gen(cid, out)


def run_analyzer(out, ref, manifest):
    p = subprocess.run([sys.executable, os.path.join(HERE, "analyze753.py"), out, ref],
                       capture_output=True, text=True, env={**os.environ, "MANIFEST_ROOT": manifest})
    v = None
    vp = os.path.join(out, "verdict.json")
    if os.path.exists(vp):
        v = json.load(open(vp))
    return p, v


def main():
    td = tempfile.mkdtemp()
    ref, out = os.path.join(td, "refs"), os.path.join(td, "out")
    os.makedirs(ref); os.makedirs(out)
    p4 = [5, 6, 7] + [330] * 18  # frozen 21-ID divergence prefix (exp752 H_1.json row)
    json.dump({"out_ids": [[5, 6, 7] + [330] * 61] * 4 + [p4] + [[5, 6, 7] + [330] * 61]},
              open(os.path.join(ref, "engine_ref.json"), "w"))
    json.dump({"out_ids": [[5, 6, 7] + [330] * 61] * 6}, open(os.path.join(ref, "hf_ref.json"), "w"))
    for f in ("analyze753.py", "infra753.inc"):
        shutil.copy(os.path.join(HERE, f), td)

    # --- A: golden path, full 8-cell set (parity gate needs >=6 non-failed) ---
    # a/b/c cells at 93.9 ms/tok = inside the frozen exp752 P4 band (93.90 +-10%).
    for c in ("hf_1", "hf_2"):
        cell(out, c, 15.87)
    for c in ("a_1", "a_2", "b_1", "b_2", "c_1", "c_2"):
        cell(out, c, 93.9)
    json.dump({"positive_control": "OK", "dispatch_capture": "CAPTURED",
               "steps": [{"step": "dispatch_capture",
                          "steps": [{"step": "replay_vs_eager", "replay_verified": True}]}]},
              open(os.path.join(out, "g_probe.json"), "w"))
    p, v = run_analyzer(out, ref, td)
    assert v, f"no verdict: {p.stdout}\n{p.stderr}"
    g = v["breakdowns"]["a_1"]
    assert v["parity"]["ok"] is True and "P4-FAIL" not in v["d1"], v["d1"]
    assert v["d2"] == "CAPTURE-OK", v["d2"]
    st = g["stages"]
    assert abs(st["de_cpu"]["med_ns"] - 1000) < 1e-6, ("de_cpu", st["de_cpu"])
    assert abs(st["hf_lat"]["med_ns"] - 1000) < 1e-6, ("hf_lat", st["hf_lat"])
    assert abs(st["out_done"]["med_ns"] - 1000) < 1e-6, ("out_done monotone pairing", st["out_done"])
    assert 4000 <= st["exec_host"]["med_ns"] <= 4100, ("exec_host", st["exec_host"])
    assert st["out_done"]["n"] == 8 * 16 * 6, ("out_done n", st["out_done"]["n"])
    # formula wiring per contrib key
    for k in ("wakeup_hit", "wakeup_fetch", "exec_host", "out_done"):
        expect = 1e-6 * st[k]["med_ns"] * st[k]["per_tok"]
        assert abs(g["contrib"][k] - expect) < 1e-9, (k, g["contrib"][k], expect)
    for k in ("de_cpu", "hf_lat", "route_q", "route_cpu", "pend_lag"):
        assert abs(g["contrib"][k] - 1e-6 * st[k]["med_ns"] * 16) < 1e-9, (k,)
    assert abs(g["wait_span_ms"] - 0.0005) < 1e-9 and abs(g["wait_tail_ms"] - 0.0004) < 1e-9
    # residual chain (R4): cm - sum(contrib, excl compl when in-wait) - wait - tail
    assert "untraced_residual" in v and v["untraced_residual"]["median"] is not None
    cm = 93.9  # a-cell med from med_t=93.9 rows
    cs = sum(g["contrib"].values())
    if any(f.startswith("COMPL-LAG-IN-WAIT:a_1") for f in v["flags"]):
        cs -= g["contrib"].get("completion_cb_lag", 0.0)
        assert g["compl_in_wait"] == 96 and g["compl_lag_dir"] == "cb-then-exit", \
            (g["compl_in_wait"], g["compl_lag_dir"])
    expect_resid = cm - cs - g["wait_span_ms"] - g["wait_tail_ms"]
    assert abs(v["untraced_residual"]["a_1"] - expect_resid) < 1e-6, \
        (v["untraced_residual"]["a_1"], expect_resid)
    assert v["d1"].startswith("gap=") and "PARITY-FAIL" not in v["d1"] and "SUSPENDED" not in v["d1"], v["d1"]
    assert v["d3"] == "OK", v["d3"]  # b/c cells identical to a by construction
    print("A golden: OK")

    # --- B: n_new != 64 rows bite ---
    ob = os.path.join(td, "out_b"); os.makedirs(ob)
    for c in ("hf_1", "hf_2"):
        cell(ob, c, 15.87)
    for c in ("a_1", "a_2"):
        cell(ob, c, 15.87, tf=3.0)
    for c in ("b_1", "b_2"):
        cell(ob, c, 12.0, n_new=14)
    p, v = run_analyzer(ob, ref, td)
    assert v, p.stderr
    assert v["d1"] == "PARITY-FAIL", v["d1"]  # early-EOS reps cannot pass parity (#1)
    assert any(f.startswith("INVALID-ROW-NNEW:b_1") for f in v["flags"]), v["flags"]
    print("B short-rows: OK")

    # --- C: engine p4 21-ID frozen prefix ACCEPTED (regression) ---
    oc = os.path.join(td, "out_c"); os.makedirs(oc)
    for c in ("hf_1", "hf_2"):
        cell(oc, c, 15.87)
    for c in ("a_1", "a_2"):
        cell(oc, c, 15.87, tf=3.0)
    for c in ("b_1", "b_2"):
        cell(oc, c, 12.0)
    for c in ("c_1", "c_2"):
        cell(oc, c, 12.0)
    p, v = run_analyzer(oc, ref, td)
    assert v, p.stderr
    assert v["parity"]["ok"] is True and v["d1"] != "PARITY-FAIL" and v["d3"] != "PARITY-FAIL", (v["d1"], v["d3"])
    print("C p4-prefix: OK")

    # --- D: failed cells excluded from parity (#5/#12) ---
    open(os.path.join(oc, "FAILED"), "w").write("a_1\n")
    p, v = run_analyzer(oc, ref, td)
    assert v, p.stderr
    assert v["parity"]["ok"] is True and v["d1"] != "PARITY-FAIL", (v["d1"], v["flags"])
    assert any(f.startswith("CELL-FAILED:a_1") for f in v["flags"]), v["flags"]
    os.remove(os.path.join(oc, "FAILED"))
    print("D failfast: OK")

    # --- E: graph positive-control FAIL -> INCONCLUSIVE-ENV ---
    json.dump({"positive_control": "FAIL", "dispatch_capture": "CAPTURED"},
              open(os.path.join(oc, "g_probe.json"), "w"))
    p, v = run_analyzer(oc, ref, td)
    assert v and v["d2"] == "INCONCLUSIVE-ENV", v["d2"]
    print("E env-gate: OK")

    # --- F: corrupted engine p4 -> PARITY-FAIL (SUB-2 #1) ---
    json.dump({"out_ids": [[5, 6, 7] + [330] * 61] * 4 + [[5, 6, 7] + [330] * 61] + [[5, 6, 7] + [330] * 61]},
              open(os.path.join(ref, "engine_ref.json"), "w"))
    p, v = run_analyzer(oc, ref, td)
    assert v and v["d1"] == "PARITY-FAIL", (v["d1"], v["flags"])
    json.dump({"out_ids": [[5, 6, 7] + [330] * 61] * 4 + [p4] + [[5, 6, 7] + [330] * 61]},
              open(os.path.join(ref, "engine_ref.json"), "w"))
    print("F p4-prefix-fail: OK")

    # --- G: TF32 enabled -> MANIP (R6) ---
    og = os.path.join(td, "out_g"); os.makedirs(og)
    for c in ("hf_1", "hf_2"):
        cell(og, c, 15.87)
    cell(og, "a_1", 15.87, tf=3.0, tf32=True)
    cell(og, "a_2", 15.87, tf=3.0)
    p, v = run_analyzer(og, ref, td)
    assert v and any(f.startswith("MANIP:TF32-ENABLED:a_1") for f in v["flags"]), v["flags"]
    assert v["manip"]["manip_ok"] is False
    print("G tf32: OK")

    # --- H: unparsable site enum -> MANIP flag, no crash (R11) ---
    mdir = os.path.join(td, "mroot"); os.makedirs(mdir)
    shutil.copy(os.path.join(HERE, "analyze753.py"), mdir)
    open(os.path.join(mdir, "infra753.inc"), "w").write("no constants here at all\n")
    p, v = run_analyzer(out, ref, mdir)
    assert v and any(f.startswith("MANIP:site-const-unverified") for f in v["flags"]), v["flags"]
    assert p.returncode == 0, (p.returncode, p.stdout[-400:], p.stderr[-400:])
    print("H bad-syntax: OK")

    # --- K: tracer drops kernels -> KERN-COVERAGE (#6) ---
    ok = os.path.join(td, "out_k"); os.makedirs(ok)
    for c in ("hf_1", "hf_2"):
        cell(ok, c, 15.87)
    for c in ("a_1", "a_2"):
        cell(ok, c, 15.87, tf=3.0)
    for c in ("b_1", "b_2"):
        cell(ok, c, 12.0)
    cell(ok, "c_1", 12.0, )
    gen("c_1", ok, drop_kern_k=6)  # rewrite c_1 trace dropping kernels k>=6
    cell(ok, "c_2", 12.0)
    p, v = run_analyzer(ok, ref, td)
    assert v and any(f.startswith("KERN-COVERAGE:c_1") for f in v["flags"]), v["flags"]
    print("K kern-coverage: OK")

    # --- M: malformed row -> ROW-SCHEMA flag, never KeyError (R14) ---
    om = os.path.join(td, "out_m"); os.makedirs(om)
    for c in ("hf_1", "hf_2"):
        cell(om, c, 15.87)
    cell(om, "a_1", 15.87, tf=3.0, no_outids=True)
    cell(om, "a_2", 15.87, tf=3.0)
    p, v = run_analyzer(om, ref, td)
    assert v and any(f.startswith("ROW-SCHEMA:a_1") for f in v["flags"]), v["flags"]
    assert p.returncode == 0
    print("M row-schema: OK")

    shutil.rmtree(td)
    print("FIXTURE-PASS (A-M)")


if __name__ == "__main__":
    main()
