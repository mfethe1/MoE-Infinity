#!/usr/bin/env python3
"""exp736 POST-HOC corrected component shares (ADDENDUM67). NOT the frozen analyzer.

Defect: prof2.py pass 4 wraps every method of each class returned by inspect.getmembers(expert_executor).
`ExpertExecutor` is an alias of `DistributedExpertExecutor` (same class object), so every method is wrapped twice
under the same key -> call counts and inclusive times in executor_wall_per_tok are 2x real (outer wrapper's
inclusive time = inner + wrapper overhead, so /2 slightly OVER-states the real time). pass4_ms_per_tok is a single
outer wall and is not affected. Pass 3 (copy trace) and the unprofiled ms/token are not affected.

Usage: corrected_shares.py RAW_OUT_DIR   (default: raw/out next to this file). Exits 1 on any failed check.
"""
import json, sys
from pathlib import Path

D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "raw" / "out"
e = json.load(open(D / "p_eng.json")); h = json.load(open(D / "p_hf.json"))
N_LAYERS = 16  # OLMoE-1B-7B: 16 MoE layers -> one wait_dispatch_local per layer per decode token
DEFECT = 2.0
ok = True
def ck(c, msg):
    global ok
    print(("CHECK-OK   " if c else "CHECK-FAIL ") + msg)
    ok &= bool(c)

ex = {r[0].split(".")[-1]: r for r in e["executor_wall_per_tok"]}
p4, p3, em, hm = e["pass4_ms_per_tok"], e["pass3_ms_per_tok"], e["ms_per_tok_unprofiled"], h["ms_per_tok_unprofiled"]
# structural evidence for the 2x: counted calls/token == 2 * layers; the unwrapped pass-3 copy trace sees exactly
# one cuda->cpu copy per layer at the _dispatch_native site (16/token) while pass 4 counts _dispatch_native 32/token.
ck(ex["wait_dispatch_local"][1] == DEFECT * N_LAYERS, f"wait_dispatch_local counted {ex['wait_dispatch_local'][1]:.0f}/tok == 2 x {N_LAYERS} layers")
ck(ex["_dispatch_native"][1] == DEFECT * N_LAYERS, f"_dispatch_native counted {ex['_dispatch_native'][1]:.0f}/tok == 2 x {N_LAYERS}")
p3_native = [r for r in e["dispatch_copies_per_tok"] if "_dispatch_native" in r[2]]
ck(len(p3_native) == 1 and p3_native[0][3] == N_LAYERS, f"pass-3 (unwrapped) _dispatch_native copies/tok = {p3_native[0][3] if p3_native else None} == {N_LAYERS}")
ck(all(r[1] == DEFECT * N_LAYERS for r in e["executor_wall_per_tok"]), "every pass-4 method counted 32/tok (uniform 2x)")

W = ex["wait_dispatch_local"][2] / DEFECT; Dd = ex["dispatch_local"][2] / DEFECT; Nn = ex["_dispatch_native"][2] / DEFECT
S = sum(r[4] for r in e["dispatch_copies_per_tok"] if r[1] == "cuda->cpu" and "_native_model_forward" in r[2])
C = sum(r[4] for r in e["dispatch_copies_per_tok"] if r[1] == "cuda->cuda"); C_hf = sum(r[4] for r in h["dispatch_copies_per_tok"] if r[1] == "cuda->cuda")
frozen = {"EXPERT-WAIT-BARRIER": ex["wait_dispatch_local"][2] / p4, "END-STEP-SYNC": S / p3,
          "DISPATCH-CALL": ex["dispatch_local"][2] / p4, "DTYPE-CASTS": max(C - C_hf, 0) / p3}
corr = {"EXPERT-WAIT-BARRIER": W / p4, "END-STEP-SYNC": S / p3, "DISPATCH-CALL": Dd / p4, "DTYPE-CASTS": max(C - C_hf, 0) / p3}
top = max(corr, key=lambda k: corr[k])
verdict = (top if corr[top] >= 0.35 else "DIFFUSE") + f"({corr[top]:.2f};unexplained~{max(1 - sum(corr.values()), 0):.2f})"
print(f"unprofiled ms/tok: engine {em:.2f} | hf {hm:.2f} | overhead {em - hm:.2f}")
print(f"pass4 total {p4:.2f} ms/tok (unaffected) | pass3 total {p3:.2f} ms/tok (tracing-inflated; hf pass3 {h['pass3_ms_per_tok']:.2f})")
print(f"corrected per token: wait_dispatch_local {W:.2f} ms ({N_LAYERS} calls, {W / N_LAYERS * 1e3:.0f} us/layer) | "
      f"dispatch_local {Dd:.2f} | _dispatch_native {Nn:.2f} | end-step logits D2H {S:.2f} | d2d casts excess {max(C - C_hf, 0):.2f}")
print("frozen shares   : " + " ".join(f"{k}={v:.2f}" for k, v in frozen.items()))
print("corrected shares: " + " ".join(f"{k}={v:.2f}" for k, v in corr.items()))
print(f"END-STEP-SYNC vs unprofiled engine ms/tok (descriptive): {S / em:.2f}")
print(f"wait share of unprofiled engine ms/tok (descriptive): {W / em:.2f}; of the engine-vs-hf overhead: {W / (em - hm):.2f}")
print(f"POST-HOC CORRECTED BUDGET: {verdict}")
ck(abs(frozen["EXPERT-WAIT-BARRIER"] - 0.6055) < 0.001, "frozen EXPERT-WAIT-BARRIER share reproduces 0.61")
ck(verdict.startswith("DIFFUSE"), "corrected reading is DIFFUSE (largest share < 0.35)")
sys.exit(0 if ok else 1)
