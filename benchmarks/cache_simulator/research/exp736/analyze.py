#!/usr/bin/env python3
"""exp736 frozen analysis. Usage: analyze.py OUTDIR  (cells.json read from OUTDIR/..)"""
import json, sys, statistics as st
from pathlib import Path
D = Path(sys.argv[1]); cells = json.load(open(D.parent / "cells.json"))
flag = set((D / "FLAGGED").read_text().split()) if (D / "FLAGGED").exists() else set()
def J(i):
    p = D / f"{i}.json"
    return json.load(open(p)) if p.exists() and p.stat().st_size else None
L = []; P = lambda s: L.append(s)
# --- unit costs
for m in ("m_g1_A", "m_g0_A", "m_g1_B"):
    r = J(m)
    if r: P(f"{m}: " + " ".join(f"{k}={v:.2f}" for k, v in r.items() if isinstance(v, float)) + (" FLAGGED" if m in flag else ""))
u = J("m_g1_A")
# --- budget (decode-only). Primary: largest engine component (pre-registered classes)
h, e = J("p_hf"), J("p_eng")
budget = "INCOMPLETE"
if h and e and u and "executor_wall_per_tok" in e:
    em, hm = e["ms_per_tok_unprofiled"], h["ms_per_tok_unprofiled"]; dms = em - hm
    ex = {r[0].split(".")[-1]: r for r in e["executor_wall_per_tok"]}
    p4 = e["pass4_ms_per_tok"]
    W = ex.get("wait_dispatch_local", [0, 0, 0.0])[2]; Dd = ex.get("dispatch_local", [0, 0, 0.0])[2]
    wc = ex.get("wait_dispatch_local", [0, 0, 0])[1]
    S = sum(r[4] for r in e["dispatch_copies_per_tok"] if r[1] == "cuda->cpu" and "_native_model_forward" in r[2])
    S_hf = sum(r[4] for r in h["dispatch_copies_per_tok"] if r[1] == "cuda->cpu")
    C = sum(r[4] for r in e["dispatch_copies_per_tok"] if r[1] == "cuda->cuda"); C_hf = sum(r[4] for r in h["dispatch_copies_per_tok"] if r[1] == "cuda->cuda")
    p3 = e["pass3_ms_per_tok"]
    P(f"hf  ms/tok={hm:.1f} aten/tok={h['aten_events_per_tok']:.0f} aten_cpu_ms/tok(profiled)={h['aten_selfcpu_ms_per_tok']:.1f} d2h-sync={S_hf:.2f} d2d-casts={C_hf:.1f}")
    P(f"eng ms/tok={em:.1f} aten/tok={e['aten_events_per_tok']:.0f} aten_cpu_ms/tok(profiled)={e['aten_selfcpu_ms_per_tok']:.1f} | overhead vs hf = {dms:.1f} ms/tok")
    P(f"eng pass4 ms/tok={p4:.1f}: wait_dispatch_local {W:.1f} ({wc:.0f} calls/tok, {100*W/p4:.0f}%) | dispatch_local {Dd:.1f} ({100*Dd/p4:.0f}%)")
    P(f"eng pass3 ms/tok={p3:.1f}: end-of-step d2h sync {S:.1f} ({100*S/p3:.0f}%) | d2d casts {C:.1f} ({100*C/p3:.0f}%)")
    P("eng executor top: " + " | ".join(f"{r[0].split('.')[-1]} {r[1]:.0f} {r[2]:.2f}" for r in e["executor_wall_per_tok"][:6]))
    P("eng dispatch top: " + " | ".join(f"{r[1]} {r[2]} {r[3]} {r[4]:.2f}" for r in e["dispatch_copies_per_tok"][:6]))
    sh = {"EXPERT-WAIT-BARRIER": W / p4, "END-STEP-SYNC": S / p3, "DISPATCH-CALL": Dd / p4, "DTYPE-CASTS": max(C - C_hf, 0) / p3}
    top = max(sh, key=sh.get); rest = 1 - sum(sh.values())
    budget = (top if sh[top] >= 0.35 else "DIFFUSE") + f"({sh[top]:.2f};unexplained~{max(rest,0):.2f})"
    P("component shares: " + " ".join(f"{k}={v:.2f}" for k, v in sh.items()))
# --- power plan ABBA (engine primary, hf secondary); clean cells only
def tps(i):
    r = J(i)
    return None if (r is None or i in flag) else st.median(x["decode_tok_s"] for x in r["rows"])
pw = {}
for arm in ("eng", "hf"):
    A = [tps(f"t1_A_{arm}"), tps(f"t4_A_{arm}")]; B = [tps(f"t2_B_{arm}"), tps(f"t3_B_{arm}")]
    P(f"power {arm}: Balanced {A} HighPerf {B}")
    if None in A or None in B: pw[arm] = "INCOMPLETE"; continue
    rat = st.mean(B) / st.mean(A); both = min(B) > max(A)
    pw[arm] = ("POWER-SENSITIVE" if rat >= 1.05 and both else "POWER-RULED-OUT" if rat < 1.05 else "POWER-AMBIGUOUS") + f"({rat:.3f})"
# --- parity: engine vs hf greedy token ids, per prompt, clean or not (correctness gate)
pe, ph = J("t1_A_eng"), J("t1_A_hf")
if pe and ph:
    same = sum(a["out_sha"] == b["out_sha"] for a, b in zip(pe["rows"], ph["rows"]))
    P(f"parity engine vs hf (t1): {same}/{len(pe['rows'])} identical greedy outputs")
P(f"FLAGGED: {' '.join(sorted(flag)) or '(none)'}")
missing = [c["id"] for c in cells if not J(c["id"])]
P(f"VERDICT BUDGET:{budget}|POWER-ENG:{pw.get('eng')}|POWER-HF:{pw.get('hf')}" + (f" [MISSING {' '.join(missing)}]" if missing else " [COMPLETE]"))
print("\n".join(L))
