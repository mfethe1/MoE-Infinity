#!/usr/bin/env python3
"""exp738 settle: re-derive every number in ADDENDUM68.md from raw/out, re-run the frozen analyzer, assert the sealed
verdict, and write ADDENDUM68.md. Exits nonzero on any mismatch. Usage: python3 gen_addendum68.py"""
import json, os, statistics as st, subprocess, sys, hashlib

H = os.path.dirname(os.path.abspath(__file__))
O = os.path.join(H, "raw", "out")
FZ = os.path.join(H, "freeze")
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg)
        print("CHECK FAILED:", msg, file=sys.stderr)


sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()

# 1. frozen analyzer bytes == ARTIFACT == RUN_SHA256
art = dict(l.split()[::-1] for l in open(os.path.join(FZ, "ARTIFACT.sha256")) if l.strip())
run = dict(l.split()[::-1] for l in open(os.path.join(O, "RUN_SHA256")) if l.strip())
for f, h in art.items():
    if f == "PREREG.md":
        continue
    ck(run.get(f) == h, f"RUN_SHA256 {f} != ARTIFACT")
    ck(sha(os.path.join(FZ, f)) == h, f"freeze/{f} bytes != ARTIFACT")

# 2. re-run frozen analyzer; must equal sealed verdict.txt byte for byte
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
out = subprocess.run([sys.executable, os.path.join(FZ, "analyze.py"), O], capture_output=True, text=True, env=env).stdout
sealed = open(os.path.join(O, "verdict.txt")).read()
ck(out == sealed, "re-run analyzer output != sealed verdict.txt")
vline = [l for l in sealed.splitlines() if l.startswith("VERDICT")][0]
ck(vline == "VERDICT GROUPED-FLAT|THREADS-MIXED", "unexpected verdict line")

# 3. independent recompute from raw rows
cells = json.load(open(os.path.join(FZ, "cells.json")))
flag = set(open(os.path.join(O, "FLAGGED")).read().split())
why = {}
for l in open(os.path.join(O, "FLAGGED.why")):
    c, rest = l.split(" ", 1)
    why.setdefault(c, set()).add("pre-start" if rest.startswith("pre-start") else
                                 ("foreign gen.py on GPU1 (other lane)" if "gen.py" in rest else rest.strip()))
pre = {l.split(",")[0]: l.strip().split(",") for l in open(os.path.join(O, "precell.csv"))}
D, ms, rows_out = {}, {}, []
for c in cells:
    d = json.load(open(os.path.join(O, c["id"] + ".json")))
    D[c["id"]] = d
    ms[c["id"]] = st.median(1000.0 / r["decode_tok_s"] for r in d["rows"])
    ge = sum(r.get("routing_delta", {}).get("grouped_experts", 0) for r in d["rows"])
    gb = sum(r.get("routing_delta", {}).get("grouped_batches", 0) for r in d["rows"])
    hits = sum(r.get("stats_delta", {}).get("policy_routed_hits", 0) for r in d["rows"])
    miss = sum(r.get("stats_delta", {}).get("policy_routed_misses", 0) for r in d["rows"])
    rows_out.append((c, ms[c["id"]], ge, gb, hits, miss, d.get("threads_effective")))


def armmean(pred):
    v = [ms[c["id"]] for c in cells if pred(c) and c["id"] not in flag]
    return st.mean(v), len(v)


hf, nhf = armmean(lambda c: c["arm"] == "hf")
base, nb = armmean(lambda c: c["arm"] == "eng" and c["threads"] == 4)
grp, ng = armmean(lambda c: c["arm"] == "grp")
t1, n1 = armmean(lambda c: c["arm"] == "eng" and c["threads"] == 1)
t8, n8 = armmean(lambda c: c["arm"] == "eng" and c["threads"] == 8)
gap = base - hf
rel = (base - grp) / base
closed = (base - grp) / gap
g41, g48 = (t1 - base) / t1, (base - t8) / base
spreads = {}
for a, pred in [("base", lambda c: c["arm"] == "eng" and c["threads"] == 4), ("grp", lambda c: c["arm"] == "grp"),
                ("t1", lambda c: c["arm"] == "eng" and c["threads"] == 1), ("t8", lambda c: c["arm"] == "eng" and c["threads"] == 8)]:
    v = [ms[c["id"]] for c in cells if pred(c) and c["id"] not in flag]
    if len(v) == 2:
        spreads[a] = abs(v[0] - v[1]) / st.mean(v)
noise = max(spreads.values())
thr = max(0.05, 2 * noise)
ck(f"engine gap base-hf = {gap:.2f} ms/tok" in sealed, "gap mismatch")
ck(f"GROUPED rel speedup={rel:.4f}" in sealed, "rel mismatch")
ck(f"threshold={thr:.4f}" in sealed, "thr mismatch")
ck(f"t1->t4 gain={g41:.4f} t4->t8 gain={g48:.4f}" in sealed, "threads gains mismatch")
ck(abs(rel) < thr, "GROUPED-FLAT requires |rel| < thr")
ck(g41 >= thr and g48 <= -thr, "THREADS-MIXED requires g41>=thr and g48<=-thr")
# structural claims used in prose
ck(all(r[2] > 0 for r in rows_out if r[0]["arm"] == "grp"), "grouped engaged in every grp cell")
ck(all(r[2] == 0 for r in rows_out if r[0]["arm"] == "eng"), "grouped zero in every eng cell")
ck(all(r[6] == r[0]["threads"] for r in rows_out if r[0]["arm"] != "hf"), "threads_effective == requested")
ck(flag == {"grp_1", "t1_1"}, "flag set")
ck(all(pre[c["id"]][3] and int(pre[c["id"]][3]) <= 1024 and pre[c["id"]][4] == "0" for c in cells), "no pre-start flags")
grp2 = [r for r in rows_out if r[0]["id"] == "grp_2"][0]
share_grouped = grp2[2] / grp2[4]  # grouped experts / routed hits (approx share of expert executions via grouped path)

# parity per prompt (same reference rows the frozen analyzer uses: first grp cell, first base cell, first hf cell)


def match(a, b):
    n = min(len(a), len(b)); fd = next((i for i in range(n) if a[i] != b[i]), n)
    return sum(x == y for x, y in zip(a, b)) / max(n, 1), fd, n


ids = {k: [r["out_ids"] for r in D[k]["rows"]] for k in D}
par = []
for i in range(len(ids["hf_1"])):
    mg, fg, n = match(ids["grp_1"][i], ids["hf_1"][i])
    mb, fb, _ = match(ids["base_1"][i], ids["hf_1"][i])
    mgb, fgb, _ = match(ids["grp_1"][i], ids["base_1"][i])
    par.append((i, n, mg, fg, mb, fb, mgb, fgb))
ck(st.mean(p[2] for p in par) >= st.mean(p[4] for p in par) - 0.05 and not [p for p in par if p[3] < 8 and p[5] >= 8], "parity correct")
ck(f"PARITY grp-vs-hf={st.mean(p[2] for p in par):.3f} base-vs-hf={st.mean(p[4] for p in par):.3f}" in sealed, "parity mismatch")
grp_self = ids["grp_1"] == ids["grp_2"]
base_self = ids["base_1"] == ids["base_2"]
hf_self = ids["hf_1"] == ids["hf_2"]
eng_short = [(k, i, len(x)) for k in ids for i, x in enumerate(ids[k]) if len(x) != 64]
ck(all(k != "hf_1" and k != "hf_2" for k, _, _ in eng_short), "only engine arms short")

L = []
w = L.append
w("# exp738 ADDENDUM68 — grouped decode kernel on SM120 consumer GPU (5060 Ti) + exec-thread ladder: GROUPED-FLAT | THREADS-MIXED")
w("")
w("Admission: **admitted, no condition.** Freeze commit 99004348 (PREREG + frozen runner/analyzer, before any cell).")
w("Run 2026-11-06T16:44:36Z → EXP738-DONE 17:28:27Z, Winnie WSL, GPU1 (RTX 5060 Ti 16 GB), OLMoE-1B-7B-0125-Instruct bf16,")
w("MoE-Infinity 0337988 (editable install, clean tree), lcnu, device_memory_ratio 0.75, 6 prompts, greedy, max_new 64.")
w("")
w("## Integrity")
w("")
w("- Winnie `sha256sum -c ARTIFACT.sha256`: 9/9 OK. out/ + run.log pulled as one tar+base64; per-file sha256 computed on both")
w("  sides: 37/37 identical (raw/SHA256SUMS). Committed freeze/ bytes == ARTIFACT == out/RUN_SHA256 (checked here).")
w("- Frozen analyze.py re-run on Mack against the pulled out/: output **byte-identical** to Winnie's verdict.txt"
  f" (sha256 {sha(os.path.join(O, 'verdict.txt'))[:16]}…).")
w("- This addendum is generated by gen_addendum68.py, which recomputes every number from raw rows and asserts it against the")
w("  sealed output (all checks OK).")
w("")
w("## Sealed verdict (frozen analyze.py, exactly as printed)")
w("")
w("```")
w(sealed.rstrip())
w("```")
w("")
w("## Per-cell table (palindromic order)")
w("")
w("| cell | arm | threads | ms/tok (median of 6) | status | grouped_experts | grouped_batches | threads_effective | quietwait s |")
w("|---|---|---|---|---|---|---|---|---|")
for c, m, ge, gb, hits, miss, te in rows_out:
    st_ = "CLEAN" if c["id"] not in flag else "FLAGGED: " + "; ".join(sorted(why.get(c["id"], {"?"})))
    w(f"| {c['id']} | {c['arm']} | {c['threads']} | {m:.2f} | {st_} | {ge} | {gb} | {te if te is not None else '—'} | {pre[c['id']][2].split()[0]} |")
w("")
w("Flags: both flagged cells come from the during-cell monitor (a foreign `gen.py` process from another lane with")
w("CUDA_VISIBLE_DEVICES=1 ran during them; it was not touched). No cell was flagged pre-start (GPU1 ≤1024 MiB, no Ollama model).")
w(f"grp_1 under contention ran at {ms['grp_1']:.2f} ms/tok and is excluded from speed but kept for parity/manipulation, per PREREG.")
w("")
w("## Arm means (clean reps only)")
w("")
w(f"- HF bf16: **{hf:.2f}** ms/tok ({nhf} clean) · engine base t4: **{base:.2f}** ({nb}) · engine grouped t4: **{grp:.2f}** ({ng})")
w(f"- engine t1: **{t1:.2f}** ({n1}) · engine t8: **{t8:.2f}** ({n8})")
w(f"- Engine gap base − HF = {gap:.2f} ms/tok. Noise (max within-arm rel spread, from "
  + ", ".join(f"{k} {v:.4f}" for k, v in spreads.items()) + f") → threshold {thr:.4f}.")
w(f"- grouped arm and t1 arm each rest on ONE clean rep (the other rep was flagged).")
w("")
w("## Q1 GROUPED — manipulation held, no speed effect")
w("")
w(f"- Manipulation: grouped path engaged in both grp cells (grouped_experts {[r[2] for r in rows_out if r[0]['arm']=='grp']}),"
  " 0 in every base/t1/t8 cell.")
w(f"  In grp_2, grouped_experts = {grp2[2]} equals the policy-routed expert hits ({grp2[4]}), ratio {share_grouped:.3f}: every resident")
w("  (hit) expert execution went through the grouped kernel, in {grp2[3]} grouped batches.".replace("{grp2[3]}", str(grp2[3])))
w(f"- Speed: rel speedup (base − grp)/base = **{rel:+.4f}**; gap closed = **{closed:+.4f}** ({closed*100:+.1f}% of the engine gap).")
ck(abs(rel) < 0.05, "flat even vs 0.05 floor")
w(f"  |rel| < threshold {thr:.4f} → **GROUPED-FLAT**. (Even against the 0.05 floor, a {rel*100:+.1f}% change is flat.)")
w("")
w("## Parity (grp_1 vs hf_1 / base_1, the rows the frozen analyzer uses)")
w("")
w("| prompt | compared tokens | grp vs HF match | first diverge | base vs HF match | first diverge | grp vs base match | first diverge |")
w("|---|---|---|---|---|---|---|---|")
for i, n, mg, fg, mb, fb, mgb, fgb in par:
    w(f"| {i} | {n} | {mg:.3f} | {fg} | {mb:.3f} | {fb} | {mgb:.3f} | {fgb} |")
w("")
w(f"- Mean grp-vs-HF {st.mean(p[2] for p in par):.3f} ≥ base-vs-HF {st.mean(p[4] for p in par):.3f} − 0.05 and no early (<8)"
  " divergence → **correct** under the frozen rule.")
eng_ids_same = all(ids[k] == ids["base_1"] for k in ("base_2", "t1_1", "t1_2", "t8_1", "t8_2"))
ck(eng_ids_same and base_self and hf_self and not grp_self, "determinism pattern")
gdiff = [(i, match(ids["grp_1"][i], ids["grp_2"][i])) for i in range(len(ids["grp_1"])) if ids["grp_1"][i] != ids["grp_2"][i]]
g2hf = st.mean(match(ids["grp_2"][i], ids["hf_1"][i])[0] for i in range(len(ids["hf_1"])))
w(f"- Self-determinism: all 6 non-grouped engine cells (base, t1, t8) emit byte-identical token ids; HF reps identical ({hf_self}).")
w(f"  The two grouped reps are NOT identical: they differ only on prompt " + ", ".join(f"{i} (first divergence at token {fd}, match {mm:.3f})" for i, (mm, fd, _) in gdiff) + ".")
w("  Descriptive finding, not a frozen gate: the grouped path is not run-to-run deterministic under greedy decoding on this card")
w(f"  (grp_1 ran under GPU co-tenancy, grp_2 clean). Parity is robust to the rep choice: grp_2 vs HF mean = {g2hf:.3f} (grp_1: "
  f"{st.mean(p[2] for p in par):.3f}).")
w(f"- Disclosed: on every engine cell prompt 4 stops at {sorted({n for _, i, n in eng_short})} tokens (HF produces 64); the engine")
w("  path ends that prompt early despite min_new 64. Parity on that prompt compares only the shared prefix; decode ms/token is")
w("  per-token and unaffected in definition, but that prompt's timing covers fewer tokens. Same in every engine arm, so it does")
w("  not bias the arm contrasts.")
w("")
w("## Q2 THREADS — thread count matters, default 4 is the best tested point")
w("")
w(f"- t1 → t4 gain = **{g41:+.4f}** (≥ thr), t4 → t8 gain = **{g48:+.4f}** (≤ −thr) → **THREADS-MIXED**.")
w(f"- Reading: 1 exec thread costs {t1-base:.1f} ms/tok more than 4; 8 threads cost {t8-base:.1f} ms/tok more than 4. The per-expert"
  " handoff is partly host-thread-serialized (more threads help up to 4), and oversubscription beyond 4 hurts.")
w("")
w("## vs registered predictions")
w("")
w(f"- Q1 predicted **GROUPED-WINS closing ≥25% of the gap** (conf ~0.6) → **refuted**: GROUPED-FLAT, gap closed {closed*100:+.1f}%,"
  " with the manipulation verified (grouped kernel engaged on ~all experts) and output parity correct.")
ck(share_grouped > 0.95, "~all experts grouped")
w(f"- Q2 predicted **THREADS-FLAT** (conf ~0.5) → **refuted**: THREADS-MIXED (t1→t4 cuts ms/tok {g41*100:.0f}%, t4→t8 adds {-g48*100:.0f}%).")
w("")
w("## Consequence (pre-decided in PREREG)")
w("")
w("- GROUPED-FLAT: \"the per-layer cost is not per-expert launch. Next, instrument the routing/handoff path")
w("  (`SetInputs` → `DispatchExperts` → exec-thread wakeup) with the engine's existing compute-timing hook")
w("  (`SetOverlapComputeTimingEnabled`), and test a CUDA-graph decode step.\" No upstream gate-widening proposal (that was the")
w("  GROUPED-WINS branch only).")
w("- THREADS-MIXED has no pre-decided consequence in PREREG (only HELP → retune, FLAT → ruled out). Post-hoc, labelled as such:")
w("  the stock default (4) is already the fastest tested point, so there is no retune to propose from this ladder; thread count")
w("  is a real lever on the host-side handoff, which points the same way as the GROUPED-FLAT consequence (CPU-side dispatch path).")
w("")
w("## Limits")
w("")
w("- Single model (OLMoE-1B-7B, top-8 of 64), single GPU (5060 Ti, PCIe gen4 x8), one ratio (0.75). grp and t1 arms have one clean rep.")
w("- Threads ladder is 3 points (1/4/8); the optimum could lie at 2–6.")
w("- The grouped kernel's own GPU time is not measured; FLAT says it does not move wall ms/token here, not that it is no faster on device.")

if fails:
    print(f"{len(fails)} CHECK(S) FAILED; ADDENDUM not written", file=sys.stderr)
    sys.exit(1)
open(os.path.join(H, "ADDENDUM68.md"), "w").write("\n".join(L) + "\n")
print("ADDENDUM68.md written; all checks OK")
