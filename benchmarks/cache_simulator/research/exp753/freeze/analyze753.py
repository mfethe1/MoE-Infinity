"""exp753 analyzer (SUB-2 fixed 2026-11-08; independent re-review fixes R1-R15).

Compute per-cell ms/tok + trace decomposition + parity + manipulation + graph probe
verdicts from raw artifacts. Analysis only; any mismatch is printed and flagged.

SUB-2 fixes (SUB2-out.md #1-#12):
  #1  parity requires n_new==64 and len==64 for EVERY row (engine prompt-4 =
      frozen 21-token-ID prefix from exp752 H_1.json; truncated/early-EOS reps
      excluded from timing entirely). #2 retire_cb_lag = RETCB(21) - max
      OUTPUT_DONE(14) <= RETCB per gen. #3 gap<=0 -> INCONCLUSIVE-gap-nonpositive.
  #4  gen keys namespaced per cell AND prompt window (per-cell trace parsing:
      no cross-cell window attribution possible); raw counter reuse flagged.
  #5  D1/D3 -> PARITY-FAIL when the parity gate fails. #6 KERN-COVERAGE on ALL
      C traces. #7 TRACE-SPAN containment (15% margins). #8 parity keyed by
      prompt_id, exactly 6 rows. #9 out_done per-token count = pair count.
  #10 untraced_residual = cell med - Sigma contributions - wait_span - wait_tail
      (contributions INCLUDE retire/completion lags; completion lag excluded
      from the sum when it sits inside the wait window - flagged, no double
      count). #11 missing refs -> MANIP flag. #12 SI map asserted vs
      infra753.inc enum (EXEC_PUSH=10, EXEC_POP=11, EXEC_FWD_ENTER=12,
      EXEC_FWD_RETURN=13); unparsable file -> MANIP flag, real mismatch -> exit 2.

Independent re-review fixes (REVIEW753-MIMO #1-#15):
  R1  production trace files are <id>.trace.jsonl (were keyed <id>.trace -> all
      decomposition silently no-op'd). R2 graph-probe step records nest one level
      (recursive flatten + top-level replay_verified fallback). R3 arm ids
      uppercased ('C' checks were dead code). R4 untraced_residual actually
      computed. R5 probe exit-code contract (crash=any nonzero child rc incl.
      negatives; missing/undecodable=1). R6 TF32 state checked (allow_tf32 must
      be False; MANIP flag otherwise). R9 pair_spans order-preserving monotone
      matching (first-b-after-a mispaired interleaved experts). R10 rows with
      n_new/len != 64 excluded from timing with INVALID-ROW flag. R11 site-const
      unparsable -> MANIP not hard-fail. R12 kernel_busy excludes failed and
      parse-failed cells. R13 missing/corrupt g_probe.json ->
      INCONCLUSIVE-NO-G-CELL / MANIP flag, never crash. R14 row schema
      mismatches flagged, never KeyError.
"""
import json, os, re, statistics as stt, sys
from collections import defaultdict


def med(x):
    x = [v for v in x if v is not None]
    return stt.median(x) if x else 0.0


# Site ids MUST match infra753.inc enum Exp753Site (asserted at startup).
SI = {
    "SETINPUTS_ENTER": 1, "SETINPUTS_EXIT": 2, "DISPATCH_ENTER": 3,
    "DISPATCH_HF_LAUNCH": 4, "ROUTE_CB_ENTER": 5, "ROUTE_CB_PUSH": 6,
    "ROUTE_FUNC_POP": 7, "RF_ENQ": 8, "ROUTE_FUNC_DONE": 9,
    "EXEC_PUSH": 10, "EXEC_POP": 11, "EXEC_FWD_ENTER": 12,
    "EXEC_FWD_RETURN": 13, "OUTPUT_DONE": 14, "KERN": 15,
    "COMPLETE_ZERO": 16, "WAIT_ENTER": 17, "WAIT_CV_WAKE": 18,
    "WAIT_EXIT": 19, "COMPLETION_CB": 20, "RETCB": 21,
}
ENUM_TO_SI = {
    "EXP753_SETINPUTS_ENTER": "SETINPUTS_ENTER", "EXP753_SETINPUTS_EXIT": "SETINPUTS_EXIT",
    "EXP753_DISPATCH_ENTER": "DISPATCH_ENTER", "EXP753_DISPATCH_HF_LAUNCH": "DISPATCH_HF_LAUNCH",
    "EXP753_ROUTE_CB_ENTER": "ROUTE_CB_ENTER", "EXP753_ROUTE_CB_PUSH": "ROUTE_CB_PUSH",
    "EXP753_ROUTE_FUNC_POP": "ROUTE_FUNC_POP", "EXP753_ROUTE_FUNC_ENQUEUE": "RF_ENQ",
    "EXP753_ROUTE_FUNC_DONE": "ROUTE_FUNC_DONE", "EXP753_EXEC_PUSH": "EXEC_PUSH",
    "EXP753_EXEC_POP": "EXEC_POP", "EXP753_EXEC_FWD_ENTER": "EXEC_FWD_ENTER",
    "EXP753_EXEC_FWD_RETURN": "EXEC_FWD_RETURN", "EXP753_EXEC_OUTPUT_DONE": "OUTPUT_DONE",
    "EXP753_KERN_SAMPLE": "KERN", "EXP753_COMPLETE_ZERO": "COMPLETE_ZERO",
    "EXP753_WAIT_ENTER": "WAIT_ENTER", "EXP753_WAIT_CV_WAKE": "WAIT_CV_WAKE",
    "EXP753_WAIT_EXIT": "WAIT_EXIT", "EXP753_COMPLETION_CB": "COMPLETION_CB",
    "EXP753_RETIRE_CB": "RETCB",
}
NLAYER = 16          # config.json num_hidden_layers (OLMoE-1B-7B-0125-Instruct)
EXPERTS_PER_TOK = 8  # num_experts_per_tok -> expert events/token ceiling 16*8=128
A_REF_BAND = (93.90 * 0.9, 93.90 * 1.1)  # P4: exp752 H band 93.90 +- 10%


def check_site_consts(flags):
    """R11: unparsable enum file -> MANIP flag + continue; real mismatch -> exit 2."""
    root = os.environ.get("MANIFEST_ROOT")
    path = os.path.join(root, "infra753.inc") if root else "infra753.inc"
    if not os.path.exists(path):
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "infra753.inc")
        path = alt if os.path.exists(alt) else None
    if path is None:
        flags.append("MANIP:site-const-unverified")
        return
    txt = open(path).read()
    found = dict(re.findall(r"(EXP753_[A-Z_]+)\s*=\s*(\d+)", txt))
    if not found:
        flags.append("MANIP:site-const-unverified")
        print("site-const: UNVERIFIED (no parsable constants in", path, ")", file=sys.stderr)
        return
    bad = []
    for ename, key in ENUM_TO_SI.items():
        if ename not in found:
            bad.append(f"{ename}:missing")
        elif int(found[ename]) != SI[key]:
            bad.append(f"{ename}:{found[ename]}!={SI[key]}")
    if bad:
        print("SITE-CONST MISMATCH vs", path, bad, file=sys.stderr)
        sys.exit(2)  # wrong constants silently re-anchor every span -> refuse to analyze
    print("site-const: verified against", path)


def load_ref(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"ref-load {path}: {e!r}", file=sys.stderr)
        return None


def parse_trace(path):
    recs = []
    with open(path) as f:
        meta = json.loads(f.readline())
        for ln in f:
            try:
                r = json.loads(ln)
            except Exception:
                continue
            recs.append((r["ns"], r["s"], r.get("e", 0), r.get("g", 0)))
    return meta, recs


def win_of(t, windows):
    for key, w0, w1 in windows:
        if w0 <= t <= w1:
            return key
    return None


# --- per-generation stage primitives (namespaced gen keys; PREREG §6/§10 defs) ---

def per_gen(recs, dec):
    d = defaultdict(list)
    for (t, s, p, g) in recs:
        if g in dec:
            d[g].append((t, s, p))
    for k in d:
        d[k].sort()
    return d


def gen_spans(pg, a, b, gap_ns=200):
    """One span per gen: first a -> first b after a+gap_ns. Returns dict gen->span."""
    out = {}
    for g, rs in pg.items():
        i0 = None
        for (t, s, p) in rs:
            if s == a and i0 is None:
                i0 = t
            elif s == b and i0 is not None and t >= i0 + gap_ns:
                out[g] = t - i0
                break
    return out


def pair_spans(pg, a, b, payload=None, gap_ns=200):
    """Order-preserving pairs (R9): each a matches the first UNUSED b at/after
    a+gap_ns in time order - correct for interleaved experts (first-b-after-a
    mispaired concurrent events). Returns (spans list, count)."""
    spans = []
    for g, rs in pg.items():
        ats = sorted(t for (t, s, p) in rs
                     if s == a and (payload is None or p in payload))
        bts = sorted(t for (t, s, p) in rs if s == b)
        used = [False] * len(bts)
        for t in ats:
            for j, t2 in enumerate(bts):
                if not used[j] and t2 >= t + gap_ns:
                    used[j] = True
                    spans.append(t2 - t)
                    break
    return spans, len(spans)


def last_pair_spans(pg, a, b, gap_ns=200):
    """Per gen: first b after the LAST a (COMPLETE_ZERO - last OUTPUT_DONE)."""
    out = {}
    for g, rs in pg.items():
        last_a = None
        for (t, s, p) in rs:
            if s == a:
                last_a = t
        if last_a is not None:
            for (t, s, p) in rs:
                if s == b and t >= last_a + gap_ns:
                    out[g] = t - last_a
                    break
    return out


def back_pair_spans(pg, b, a):
    """Per record of site b: b.t - max{a.t <= b.t} in same gen (fix #2: 21-last 14)."""
    out = []
    for g, rs in pg.items():
        for (t, s, p) in rs:
            if s == b:
                prev = [t2 for (t2, s2, p2) in rs if s2 == a and t2 <= t]
                if prev:
                    out.append(t - max(prev))
    return out


def gen_in_wait(pg):
    """Per gen: (first WAIT_ENTER, last WAIT_EXIT) for inside-wait detection."""
    out = {}
    for g, rs in pg.items():
        e = [t for (t, s, p) in rs if s == SI["WAIT_ENTER"]]
        x = [t for (t, s, p) in rs if s == SI["WAIT_EXIT"]]
        if e and x:
            out[g] = (min(e), max(x))
    return out


def flatten_steps(obj):
    """R2: collect every {"step": ...} record recursively (drivers nest child
    step lists one level down)."""
    found = []
    if isinstance(obj, dict):
        if "step" in obj:
            found.append(obj)
        for v in obj.values():
            found.extend(flatten_steps(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(flatten_steps(v))
    return found


def breakdowns(outs):
    """Per-cell decomposition. Each cell's trace is parsed against ITS OWN
    prompt windows (fix #4): no cross-cell window attribution is possible."""
    cells, metas = {}, {}
    g_toks = 0.0
    any_reset = False
    for cid in sorted(outs):
        if not cid.startswith(("a_", "b_", "c_")):
            continue
        try:
            r = json.loads(outs[cid]["json"])
        except Exception:
            continue
        p = outs[cid].get("jsonl")
        if not p:
            continue
        meta, recs = parse_trace(p)
        metas[cid] = meta
        windows = [(row["i"],) + tuple(row["win_mono"])
                   for row in r["rows"]
                   if row.get("win_mono") and len(row["win_mono"]) == 2]
        rawmap = defaultdict(set)
        nrec = []
        for (t, s, pp, g) in recs:
            wkey = win_of(t, windows)  # full-run windows only; probe/warmup -> "x"
            key = (wkey if wkey is not None else "x", g)
            if wkey is not None:
                rawmap[g].add(wkey)
            nrec.append((t, s, pp, key))
        reset_seen = any(len(v) > 1 for v in rawmap.values())
        any_reset = any_reset or reset_seen
        enq_per_gen = defaultdict(int)
        for (t, s, pp, g) in nrec:
            if s == SI["RF_ENQ"]:
                enq_per_gen[g] += 1
        dec = {g for g, n in enq_per_gen.items() if 1 <= n <= 8 and g[0] != "x"}
        ctoks = len(dec) / NLAYER if dec else 0  # decode gens / num_hidden_layers
        g_toks += ctoks
        inwin = [(t, s, pp, g) for (t, s, pp, g) in nrec if g[0] != "x"]
        pg = per_gen(inwin, dec)
        tp = {}
        for nm, (a, b) in {"de_cpu": (SI["DISPATCH_ENTER"], SI["DISPATCH_HF_LAUNCH"]),
                           "hf_lat": (SI["DISPATCH_HF_LAUNCH"], SI["ROUTE_CB_ENTER"]),
                           "route_q": (SI["ROUTE_CB_PUSH"], SI["ROUTE_FUNC_POP"]),
                           "route_cpu": (SI["ROUTE_FUNC_POP"], SI["ROUTE_FUNC_DONE"]),
                           }.items():
            sp = gen_spans(pg, a, b)
            tp[nm] = {"med_ns": med(list(sp.values())), "n": len(sp),
                      "per_tok": len(sp) / ctoks if ctoks else 0}
        wh, n_hit = pair_spans(pg, SI["EXEC_PUSH"], SI["EXEC_POP"], payload={1})
        wf, n_fetch = pair_spans(pg, SI["EXEC_PUSH"], SI["EXEC_POP"], payload={2, 3})
        eh, n_eh = pair_spans(pg, SI["EXEC_POP"], SI["EXEC_FWD_RETURN"])
        od, n_od = pair_spans(pg, SI["EXEC_FWD_RETURN"], SI["OUTPUT_DONE"])
        for nm, arr, n in (("wakeup_hit", wh, n_hit), ("wakeup_fetch", wf, n_fetch),
                           ("exec_host", eh, n_eh), ("out_done", od, n_od)):
            tp[nm] = {"med_ns": med(arr), "n": n,
                      "per_tok": n / ctoks if ctoks else 0}
        pl = last_pair_spans(pg, SI["OUTPUT_DONE"], SI["COMPLETE_ZERO"])
        tp["pend_lag"] = {"med_ns": med(list(pl.values())), "n": len(pl),
                          "per_tok": len(pl) / ctoks if ctoks else 0}
        ws = gen_spans(pg, SI["WAIT_ENTER"], SI["WAIT_CV_WAKE"])
        wt = gen_spans(pg, SI["WAIT_CV_WAKE"], SI["WAIT_EXIT"])
        rcb = back_pair_spans(pg, SI["RETCB"], SI["OUTPUT_DONE"])
        # completion_cb_lag: both directions possible; PREREG §10.2 literal is
        # COMPLETION_CB(20) - WAIT_EXIT(19) (cb after exit). If the trace shows
        # cb BEFORE exit (inside the wait window), the lag is reported but
        # flagged COMPL-LAG-IN-WAIT and excluded from the residual chain (no
        # double count with wait_span).
        ccb_after = back_pair_spans(pg, SI["COMPLETION_CB"], SI["WAIT_EXIT"])
        ccb_inwin = 0
        if ccb_after:
            ccb, n_ccb, ccb_dir = ccb_after, len(ccb_after), "after-wait-exit"
        else:
            ccb, n_ccb = pair_spans(pg, SI["COMPLETION_CB"], SI["WAIT_EXIT"])
            ccb_dir = "cb-then-exit" if n_ccb else "none"
        iw = gen_in_wait(pg)
        for g, rs in pg.items():
            if g in iw:
                w0, w1 = iw[g]
                if any(s == SI["COMPLETION_CB"] and w0 <= t <= w1 for (t, s, p) in rs):
                    ccb_inwin += 1
        wait_span = med(list(ws.values())) if ws else 0.0
        wait_tail = med(list(wt.values())) if wt else 0.0

        def contrib(key, mul):
            return 1e-6 * tp[key]["med_ns"] * mul
        genk = ("de_cpu", "hf_lat", "route_q", "route_cpu", "pend_lag")
        expk = ("wakeup_hit", "wakeup_fetch", "exec_host", "out_done")
        cc = {k: contrib(k, NLAYER) for k in genk}
        cc.update({k: contrib(k, tp[k]["per_tok"]) for k in expk})
        cc["retire_cb_lag"] = 1e-6 * med(rcb) * (len(rcb) / ctoks if ctoks else 0)
        cc["completion_cb_lag"] = 1e-6 * med(ccb) * (n_ccb / ctoks if ctoks else 0)
        kern_dec = [rr for rr in inwin if rr[1] == SI["KERN"] and rr[3] in dec]
        enq_dec = [rr for rr in inwin if rr[1] == SI["RF_ENQ"] and rr[3] in dec]
        cells[cid] = {"meta": meta, "stages": tp,
                      "wait_span_ms": 1e-6 * wait_span, "wait_tail_ms": 1e-6 * wait_tail,
                      "contrib": cc, "toks": ctoks, "dec_gens": len(dec),
                      "kern_sum_ms": 1e-6 * sum(rr[2] for rr in kern_dec),
                      "kern_n": len(kern_dec), "enq_dec_n": len(enq_dec),
                      "gen_reset_seen": reset_seen,
                      "compl_lag_dir": ccb_dir, "compl_in_wait": ccb_inwin,
                      "counts_per_tok": {k: tp[k]["per_tok"] for k in list(genk) + list(expk)}}
    return cells, metas, g_toks, {}, any_reset


def main():
    outdir, refdir = sys.argv[1], sys.argv[2]
    flags = []
    check_site_consts(flags)
    outs = {}
    for f in sorted(os.listdir(outdir)):
        base, _, ext = f.rpartition(".")
        if ext == "jsonl" and base.endswith(".trace"):
            base = base[:-6]  # R1: production writes <id>.trace.jsonl
        if ext in ("json", "log", "jsonl") and not base.startswith(
                ("verdict", "RUN_SHA", "ENV", "precell", "SMOKE")):
            outs.setdefault(base, {})
            if ext == "jsonl":
                outs[base]["jsonl"] = os.path.join(outdir, f)
            else:
                outs[base][ext] = open(os.path.join(outdir, f)).read()
    failed = set()
    fp = os.path.join(outdir, "FAILED")
    if os.path.exists(fp):
        failed = {ln.strip() for ln in open(fp) if ln.strip()}
    parse_failed = set()
    cells, metas, toks, _counts, reset_seen = breakdowns(outs)
    if reset_seen:
        flags.append("GEN-COUNTER-RESET-SEEN")  # informational: namespacing applied
    engine_ref = load_ref(os.path.join(refdir, "engine_ref.json"))
    hf_ref = load_ref(os.path.join(refdir, "hf_ref.json"))
    print(f"global: trace_records={sum(m.get('records', 0) for m in metas.values())} "
          f"decode_gens={sum(c['dec_gens'] for c in cells.values())} toks={toks}")
    verdict = {"parity": {}, "manip": {}, "d1": None, "d2": None, "d3": None, "flags": flags,
               "breakdowns": cells}
    hf_vals, a_vals, bc_vals = [], [], []
    cell_ms = {}
    parities, flagstat = {}, {}
    for cid in sorted(outs):
        arm = cid.split("_")[0].upper()  # R3
        if cid == "g_probe" or not cid.endswith(("_1", "_2")):
            continue
        c = outs[cid]
        flagged = os.path.exists(os.path.join(outdir, "FLAGGED")) and \
            any(ln.strip() == cid for ln in open(os.path.join(outdir, "FLAGGED")))
        flagstat[cid] = flagged
        excluded = flagged or cid in failed
        if cid in failed:
            flags.append(f"CELL-FAILED:{cid}")
        try:
            r = json.loads(c["json"])
        except Exception as e:
            flags.append(f"PARSE:{cid}:{e!r}")
            parse_failed.add(cid)
            continue
        # R6: TF32 must be off (ERRATUM-752-TR32); state recorded by harness.
        atf = r.get("allow_tf32") or {}
        if atf.get("matmul") or atf.get("cudnn"):
            flags.append(f"MANIP:TF32-ENABLED:{cid}:{atf}")
        # --- parity (fixes #1/#8 + R14: schema-safe) ---
        rows = r["rows"]
        by_id = {}
        for row in rows:
            by_id.setdefault(row.get("i"), []).append(row)
        pstat, pnotes = [True] * 6, []
        if sorted(k for k in by_id if k is not None) != list(range(6)) or len(rows) != 6:
            pstat = [False] * 6
            pnotes.append(f"rows:{len(rows)} ids:{sorted(by_id.keys())}")
        ref = hf_ref if arm == "HF" else engine_ref
        if ref is None:
            flags.append(f"MANIP:ref-missing:{cid}")
            pstat = [False] * 6
            pnotes.append("ref-missing")
        else:
            for i in range(6):
                row = by_id.get(i, [None])[0]
                rid = ref["out_ids"][i] if i < len(ref.get("out_ids", [])) else None
                if row is None or rid is None:
                    pstat[i] = False
                    continue
                got = row.get("out_ids")
                nnew = row.get("n_new")
                if not isinstance(got, list) or nnew is None:
                    pstat[i] = False
                    pnotes.append(f"p{i}:row-schema")
                    continue
                if arm == "HF":
                    ok = (got == rid and nnew == 64 and len(got) == 64)
                elif i == 4:
                    # engine prompt-4: frozen 21-token-ID divergence prefix
                    # (engine_ref p4 = exp752 H_1.json row; exp753 forces 64 new
                    # tokens via min_new_tokens=64).
                    ok = (nnew == 64 and len(got) == 64 and len(rid) == 21
                          and got[:21] == rid)
                else:
                    ok = (got == rid and nnew == 64 and len(got) == 64)
                if not ok:
                    pstat[i] = False
                    pnotes.append(f"p{i}:n_new={nnew},len={len(got)},ref_len={len(rid)}")
        parities[cid] = pstat
        # --- row-level timing (R10: only full 64-token rows enter medians) ---
        vals = []
        for row in rows:
            nnew = row.get("n_new")
            got = row.get("out_ids")
            if not isinstance(got, list) or nnew is None:
                flags.append(f"ROW-SCHEMA:{cid}:p{row.get('i')}")
                continue
            if nnew != 64 or len(got) != 64:
                flags.append(f"INVALID-ROW-NNEW:{cid}:p{row.get('i')}:n_new={nnew},len={len(got)}")
                continue
            dt_raw = row.get("t_full_s", 0) - row.get("t_1tok_s", 0)
            if dt_raw <= 0:
                flags.append(f"DECODE-DELTA-NONPOSITIVE:{cid}:p{row.get('i')}")
                continue
            vals.append(1000 * dt_raw / (nnew - 1))
        if vals:
            cm = med(vals)
            cell_ms[cid] = cm
            if len(vals) < 3:
                flags.append(f"INVALID-ROWS:{cid}:n={len(vals)}")
        else:
            cm = None
        if arm == "HF":
            if cm and not excluded:
                hf_vals.append(cm)
        else:
            t1s = [row.get("t_1tok_s", 0) for row in rows if row.get("t_1tok_s", 0) > 0]
            if t1s:
                m1 = med(t1s)
                if m1 > 0 and any(abs(t - m1) / m1 > 0.20 for t in t1s):
                    flags.append(f"PROBE-PREFILL-DRIFT:{cid}")
            if cm and not excluded:
                a_vals.append(cm) if arm == "A" else bc_vals.append((arm, cm))
    # --- trace checks + kernel coverage (fix #6 all C; fix #7 TRACE-SPAN) ---
    for cid, cell in cells.items():
        arm = cid.split("_")[0].upper()  # R3
        meta = metas.get(cid, cell.get("meta", {}))
        if meta.get("dropped", 0):
            flags.append(f"RING-DROPPED:{cid}:{meta.get('dropped')}")
        p = outs[cid].get("jsonl")
        if not p:
            continue
        _, recs = parse_trace(p)
        cov = {}
        for (t, s, pr, g) in recs:
            cov[s] = cov.get(s, 0) + 1
        missing = [s for s in list(range(1, 15)) + list(range(16, 22))
                   if arm in ("B", "C") and cov.get(s, 0) == 0]
        if missing:
            flags.append(f"SITE-MISSING:{cid}:{missing}")
        if arm == "C":
            enq, kern = cell["enq_dec_n"], cell["kern_n"]
            if enq > 0 and abs(kern - enq) / enq > 0.01:
                flags.append(f"KERN-COVERAGE:{cid}:{kern}/{enq}")
        if cell.get("compl_in_wait", 0) > 0:
            flags.append(f"COMPL-LAG-IN-WAIT:{cid}:{cell['compl_in_wait']}")
        if arm in ("A", "B", "C"):
            rows = json.loads(outs[cid]["json"])["rows"]
            for row in rows:
                wm = row.get("win_mono")
                if not wm or len(wm) != 2:
                    continue
                w0, w1 = wm
                if w1 <= w0:
                    continue
                inw = [t for (t, s, pr, g) in recs if w0 <= t <= w1]
                if not inw:
                    flags.append(f"TRACE-SPAN:{cid}:p{row['i']}:empty")
                    continue
                marg = 0.15 * (w1 - w0)
                if min(inw) > w0 + marg or max(inw) < w1 - marg:
                    flags.append(f"TRACE-SPAN:{cid}:p{row['i']}:"
                                 f"{min(inw)-w0:.0f}..{w1-max(inw):.0f}ns")
    # --- G-M: RUN_SHA256 self-identity ---
    shap = os.path.join(outdir, "RUN_SHA256")
    if os.path.exists(shap):
        import hashlib
        for ln in open(shap):
            parts = ln.split()
            if len(parts) >= 2:
                h, fn = parts[0], parts[-1]
                fn2 = fn.split("/")[-1]
                hit = None
                for base in [outdir, refdir, os.path.dirname(outdir.rstrip("/")), "."]:
                    for cand in (os.path.join(base, fn), os.path.join(base, fn2)):
                        if os.path.exists(cand):
                            hit = cand
                            break
                    if hit:
                        break
                if hit:
                    hh = hashlib.sha256(open(hit, "rb").read()).hexdigest()
                    if hh != h:
                        flags.append(f"SHA256-MISMATCH:{fn}:{h}!={hh}")
                else:
                    flags.append(f"SHA256-FILE-MISSING:{fn}")
    manip = not any(f.startswith(("MANIP", "RING-DROPPED", "SITE-MISSING",
                                  "SHA256", "TRACE-SPAN")) for f in flags)
    verdict["manip"]["manip_ok"] = manip
    verdict["manip"]["flags"] = flags
    # --- parity aggregate (R12: failed AND parse-failed excluded) ---
    non_failed = {cid: p for cid, p in parities.items()
                  if cid not in failed and cid not in parse_failed}
    parity_ok = (bool(non_failed) and all(all(v) for v in non_failed.values())
                 and len(non_failed) >= 6)
    verdict["parity"] = {"per_cell": parities, "ok": parity_ok,
                         "compared": sorted(non_failed)}
    # --- D1 (suppressed on parity fail, fix #5) ---
    gap = (med(a_vals) - med(hf_vals)) if (a_vals and hf_vals) else None
    if not parity_ok:
        verdict["d1"] = "PARITY-FAIL"
    elif gap is None:
        verdict["d1"] = "INCONCLUSIVE-no-clean-cells"
        flags.append("NO-CLEAN-CELLS")
    elif gap <= 0:
        verdict["d1"] = "INCONCLUSIVE-gap-nonpositive"
        flags.append("GAP-NONPOSITIVE")
    else:
        # R12: clean C set excludes FLAGGED, failed and parse-failed cells.
        ccids = [c for c in cells
                 if c.startswith("c_") and not flagstat.get(c)
                 and c not in failed and c not in parse_failed]
        ksum = sum(cells[c]["kern_sum_ms"] for c in ccids)
        ttoks = sum(cells[c]["toks"] for c in ccids)
        kb = ksum / ttoks if ttoks else None
        ratio = kb / gap if kb is not None else None
        d1 = f"gap={gap:.2f}ms tok kernel_busy={kb:.2f}ms tok ratio={ratio:.2f}" \
            if ratio is not None else f"gap={gap:.2f}ms tok kernel_busy=NA"
        verdict["d1"] = d1 + " " + (
            "KERNEL-BOUND" if ratio is not None and ratio >= 0.5 else
            "HANDOFF-BOUND" if ratio is not None and ratio <= 0.3 else
            "MIXED" if ratio is not None else "INCONCLUSIVE-NO-C")
        if not (A_REF_BAND[0] <= med(a_vals) <= A_REF_BAND[1]):
            flags.append("P4-DRIFT")
            verdict["d1"] += ";SUSPENDED-P4-DRIFT"
    # --- untraced_residual (fix #10 / R4): per clean A cell + aggregate ---
    resids = {}
    for cid in sorted(cell_ms):
        cell = cells.get(cid)
        if (cid.startswith("a_") and cell and not flagstat.get(cid)
                and cid not in failed and cid not in parse_failed):
            cs = sum(cell["contrib"].values())
            if any(f.startswith(f"COMPL-LAG-IN-WAIT:{cid}") for f in flags):
                cs -= cell["contrib"].get("completion_cb_lag", 0.0)
            resids[cid] = cell_ms[cid] - cs - cell["wait_span_ms"] - cell["wait_tail_ms"]
    verdict["untraced_residual"] = dict(resids)
    if resids:
        verdict["untraced_residual"]["median"] = med(list(resids.values()))
        verdict["untraced_residual"]["clean_cells"] = sorted(resids)
    # --- D2 graph probe (R2 flatten; R13 missing/corrupt -> NO-G-CELL) ---
    gp = {}
    if "g_probe" in outs and "json" in outs["g_probe"]:
        try:
            gp = json.loads(outs["g_probe"]["json"])
        except Exception as e:
            flags.append(f"MANIP:g-probe-undecodable:{e!r}")
    allsteps = flatten_steps(gp)
    replay_ok = any(s.get("step") == "replay_vs_eager" and s.get("replay_verified") is True
                    for s in allsteps) or gp.get("replay_verified") is True
    if not gp:
        verdict["d2"] = "INCONCLUSIVE-NO-G-CELL"
    elif gp.get("positive_control") != "OK":
        verdict["d2"] = "INCONCLUSIVE-ENV"
    elif gp.get("dispatch_capture") == "CAPTURED" and replay_ok:
        verdict["d2"] = "CAPTURE-OK"
    elif gp.get("dispatch_capture"):
        verdict["d2"] = f"CAPTURE-FAIL@{gp.get('dispatch_capture')}"
    else:
        verdict["d2"] = "INCONCLUSIVE-NO-G-CELL"
    # --- D3 (suppressed on parity fail, fix #5) ---
    if not parity_ok:
        verdict["d3"] = "PARITY-FAIL"
    elif not a_vals or not bc_vals:
        verdict["d3"] = "INCONCLUSIVE-no-clean-cells"
    else:
        for arm, v in bc_vals:
            pert = abs(v - med(a_vals)) / med(a_vals) if med(a_vals) else 0
            if pert > 0.05:
                verdict.setdefault("d3_flags", []).append(f"{arm}:{pert:.2f}")
        verdict["d3"] = "OK" if not verdict.get("d3_flags") else "PERTURBS " + " ".join(verdict["d3_flags"])
    print(json.dumps({k: v for k, v in verdict.items() if k != "breakdowns"}, indent=1, default=str))
    for cid, c in sorted(cells.items()):
        st = c["stages"]
        print(f"{cid}: toks={c['toks']:.1f} de_cpu={st['de_cpu']['med_ns']/1000:.1f}us "
              f"hf_lat={st['hf_lat']['med_ns']/1000:.1f}us route_cpu={st['route_cpu']['med_ns']/1000:.1f}us "
              f"wake_hit={st['wakeup_hit']['med_ns']/1000:.1f}us wake_fetch={st['wakeup_fetch']['med_ns']/1000:.1f}us "
              f"exec_host={st['exec_host']['med_ns']/1000:.1f}us out_done={st['out_done']['med_ns']/1000:.1f}us "
              f"pend={st['pend_lag']['med_ns']/1000:.1f}us wait={c['wait_span_ms']:.3f}ms "
              f"tail={c['wait_tail_ms']:.3f}ms kern={c['kern_sum_ms']:.2f}ms")
    json.dump(verdict, open(os.path.join(outdir, "verdict.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
