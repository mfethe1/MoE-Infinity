#!/usr/bin/env python3
"""exp760 analyzer — derived from exp760 analyzer A2 (proven, fixture-reviewed) with one addition:
per-cell RC-banner identity check (log must contain "exp752 mode=2"; absence = invalid cell).
Base provenance (exp760 A2): verdict logic per PREREG.md with the A2 fixes
(freeze: FREEZE-757-A2.txt; review: REVIEW-757-raw.txt REJECT defects 1-5,7-9 + DRIFT fixes).
A2 changes vs frozen v1: (D1) row validity judged against the sealed refs' shape (prompt 4 EOS at 21
tokens is natural; n_new<64 is NOT invalidity); (D2) foreign compute-app exclusion applies to ALL arms;
(D3) G/CG manip check adds NVML util mean >= 20%; (D4) missing/short mon.csv fails closed; (D5) precell
Runner.Worker / foreign-prestart / gpu-prestart / ollama-prestart exclude in every arm; (D7) empty
col.pid fails the manip check instead of crashing; (D8) a row missing out_ids invalidates the cell
(fail-closed, never counted as divergence); (D9) resolved: any Q-vs-refs or Q-vs-Q disagreement is
ANCHOR-FAIL (exit 2), never DIVERGENCE-REPRODUCED. DRIFT: divergence report now includes per-prompt
out_sha, routing counters and seam-mate out_sha. Labels 'short-run', 'util-samples<10', 'q-loadavg>4',
'manip-fail-cpu(...)', 'manip-fail-gpu(...)' are asserted by the fixture suites and kept stable.
Usage: python3 analyze757.py <out-dir> [--refs refs]
Exit: 0=verdict issued clean, 4=verdict with invalid cells, 2=ANCHOR-FAIL, 3=no valid anchor data."""
import json, sys, os, math

ARMS = {"Q": ["Q1", "Q2", "Q3"], "C": ["C1", "C2", "C3"], "G": ["G1", "G2", "G3"], "CG": ["CG1", "CG2", "CG3"]}
OWN_PIDS_FILES = ("eng.pid", "col.pid")  # out/<ID>.eng.pid / out/<ID>.col.pid: our own compute apps
MON_MIN_SAMPLES = 3
UTIL_MIN_SAMPLES = 10
GPU_UTIL_MEAN_MIN = 20.0  # G/CG manip check (PREREG)


def load_refs(refdir):
    r2 = json.load(open(os.path.join(refdir, "RC_2.json")))
    r3 = json.load(open(os.path.join(refdir, "RC_3.json")))
    v2 = [r["out_ids"] for r in r2["rows"]]
    v3 = [r["out_ids"] for r in r3["rows"]]
    if v2 != v3:
        raise SystemExit("FATAL: sealed refs RC_2/RC_3 disagree; cannot anchor")
    return v2


def cp_upper(n, k, conf=0.95):
    """One-sided Clopper-Pearson upper bound on p given k events in n trials (bisection on P(X<=k))."""
    if n == 0:
        return None
    if k == n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        s = sum(math.comb(n, i) * mid**i * (1 - mid) ** (n - i) for i in range(k + 1))
        if s > (1 - conf):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def util_stats(path):
    """nvsamp.py format: epoch_s,util_gpu_pct,mem_used_mib (no header). Returns (n, mean_util)."""
    vals = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.split(",")
                if len(parts) >= 2:
                    try:
                        vals.append(float(parts[1]))
                    except ValueError:
                        pass
    except OSError:
        return 0, None
    return len(vals), (sum(vals) / len(vals) if vals else None)


def mon_loadavg_mean(path):
    """mon757.sh format: ts,la1;la2;la3,mem,ol,apps. Returns (n_samples, mean_1min)."""
    vals = []
    try:
        with open(path) as f:
            for line in f:
                parts = line.split(",")
                if len(parts) >= 2:
                    try:
                        vals.append(float(parts[1].replace(";", " ").split()[0]))
                    except (ValueError, IndexError):
                        pass
    except OSError:
        return 0, None
    return len(vals), (sum(vals) / len(vals) if vals else None)


def apps_trace(path, own_pids):
    """Parse mon csv last column (pid[,mem] entries joined by '|').
    Returns (own_seen, foreign_seen) PID sets from nvidia-smi compute-apps samples."""
    own_seen, foreign_seen = set(), set()
    try:
        with open(path) as f:
            for line in f:
                cols = line.rstrip("\n").split(",")
                if len(cols) < 5:
                    continue
                for entry in cols[-1].split("|"):
                    entry = entry.strip()
                    if not entry:
                        continue
                    pid = entry.split(",")[0].strip()
                    if pid in own_pids:
                        own_seen.add(pid)
                    else:
                        foreign_seen.add(pid)
    except OSError:
        pass
    return own_seen, foreign_seen


def first_token_diff(a, b):
    for j in range(min(len(a), len(b))):
        if a[j] != b[j]:
            return j, a[j], b[j]
    j = min(len(a), len(b))
    return j, (a[j] if j < len(a) else None), (b[j] if j < len(b) else None)


def read_precell(outdir):
    """precell.csv: ID,QW,MG,OL,LA,RW,FA -> {id: dict}. Missing file -> {} (skip, disclosed)."""
    res = {}
    p = os.path.join(outdir, "precell.csv")
    try:
        with open(p) as f:
            for line in f:
                c = line.strip().split(",")
                if len(c) >= 7:
                    try:
                        res[c[0]] = {"qw": c[1], "mg": int(c[2]), "ol": int(c[3]),
                                     "rw": int(c[5]), "fa": int(c[6])}
                    except ValueError:
                        pass
    except OSError:
        pass
    return res


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "out"
    refdir = "refs"
    if "--refs" in sys.argv:
        refdir = sys.argv[sys.argv.index("--refs") + 1]
    refs = load_refs(refdir)
    flagged = set()
    fp = os.path.join(outdir, "FLAGGED")
    if os.path.exists(fp):
        flagged = {l.strip() for l in open(fp) if l.strip()}
    precell = read_precell(outdir)

    report, invalid = {}, {}
    for arm, ids in ARMS.items():
        for cid in ids:
            p = os.path.join(outdir, cid + ".json")
            if not os.path.exists(p):
                invalid[cid] = "missing-out"
                continue
            d = json.load(open(p))
            rows = d.get("rows", [])
            reasons = []
            if cid in flagged:
                reasons.append("flagged-precell")
            pc = precell.get(cid)
            if pc is not None:
                if pc["rw"] > 0:
                    reasons.append("runner-worker")
                if pc["fa"] > 0:
                    reasons.append("foreign-prestart")
                if pc["mg"] > 1024:
                    reasons.append("gpu-prestart")
                if pc["ol"] != 0:
                    reasons.append("ollama-prestart")
            if len(rows) != 6:
                reasons.append("short-run")
            # D8: fail closed on missing out_ids (never counted as divergence)
            if any(r.get("out_ids") is None for r in rows):
                reasons.append("missing-out-ids")
            # exp760 addition: RC-arm identity banner (PREREG: every cell must show mode=2)
            logp = os.path.join(outdir, cid + ".log")
            try:
                with open(logp, errors="replace") as f:
                    logtxt = f.read()
                if "exp752 mode=2" not in logtxt:
                    reasons.append("no-rc-banner")
            except OSError:
                reasons.append("no-log")
            n_util, util_mean = util_stats(os.path.join(outdir, cid + ".util.csv"))
            if n_util < UTIL_MIN_SAMPLES:
                reasons.append("util-samples<10")
            n_mon, la = mon_loadavg_mean(os.path.join(outdir, cid + ".mon.csv"))
            if n_mon < MON_MIN_SAMPLES:
                reasons.append("mon-missing")
            own_pids = set()
            for suf in OWN_PIDS_FILES:
                pp = os.path.join(outdir, cid + "." + suf)
                if os.path.exists(pp):
                    for tok in open(pp).read().split():
                        if tok.isdigit():
                            own_pids.add(tok)
            own_seen, foreign_seen = apps_trace(os.path.join(outdir, cid + ".mon.csv"), own_pids)
            # D2/D5: uncontrolled foreign compute apps exclude in EVERY arm (PREREG: uncontrolled
            # factors exclude in all arms; only our registered manipulations are treatment).
            if foreign_seen:
                reasons.append(("q-foreign-app:" if arm == "Q" else "foreign-app:") + ";".join(sorted(foreign_seen)))
            if arm == "Q":
                if la is not None and la > 4.0:
                    reasons.append("q-loadavg>4")
            else:
                if arm in ("C", "CG") and (la is None or la < 8.0):
                    reasons.append("manip-fail-cpu(loadavg mean < 8)")
                if arm in ("G", "CG"):
                    col_pid = ""
                    pp = os.path.join(outdir, cid + ".col.pid")
                    if os.path.exists(pp):
                        toks = [t for t in open(pp).read().split() if t.isdigit()]
                        col_pid = toks[0] if toks else ""
                    if not col_pid or col_pid not in own_seen:
                        reasons.append("manip-fail-gpu(co-tenant absent)")
                    elif util_mean is None or util_mean < GPU_UTIL_MEAN_MIN:
                        reasons.append("manip-fail-gpu(util mean < 20)")
            out_ids = [r.get("out_ids") for r in rows]
            diverged = [i for i, v in enumerate(out_ids) if v is not None and i < len(refs) and v != refs[i]]
            rt = {}
            for r in rows:
                for k, v in (r.get("routing_delta") or {}).items():
                    if isinstance(v, (int, float)):
                        rt[k] = rt.get(k, 0) + v
            report[cid] = {"arm": arm, "valid": not reasons, "why": reasons, "loadavg_mean": la,
                           "util_mean": util_mean,
                           "diverged_prompts": diverged,
                           "out_sha": [r.get("out_sha") for r in rows],
                           "counters": {k: sum(r.get("stats_delta", {}).get(k, 0) for r in rows)
                                        for k in ("route_failures", "comp_retired") if rows},
                           "routing": rt,
                           "own_seen": sorted(own_seen), "foreign_seen": sorted(foreign_seen),
                           "qw": pc["qw"] if pc else "?"}
            if reasons:
                invalid[cid] = ";".join(reasons)

    q_valid = [c for c in ARMS["Q"] if report.get(c, {}).get("valid")]
    # D9 (A2 resolution): any valid Q disagreement with the sealed refs (which includes Q-vs-Q
    # disagreement, since both are compared to the same refs) is ANCHOR-FAIL, never a divergence.
    anchor_bad = [c for c in q_valid if report[c]["diverged_prompts"]]
    if anchor_bad:
        print("VERDICT: ANCHOR-FAIL (Q cells not byte-identical to sealed refs):", anchor_bad)
        for c in anchor_bad:
            print(c, report[c])
        print("No determinism verdict issued (prereg). Raw data stands.")
        sys.exit(2)
    if not q_valid:
        print("VERDICT: NO-VALID-DATA (no valid Q anchor cell)")
        sys.exit(3)

    div_cells = [(c, report[c]) for c in report if report[c]["valid"] and report[c]["diverged_prompts"]]
    print("== exp760 verdict (analyzer A2) ==")
    print("anchor: valid Q cells", q_valid, "== sealed refs (byte-identical)")
    print("cells (valid/total per arm): " + ", ".join(
        f"{a}:{sum(1 for c in ids if report.get(c, {}).get('valid'))}/{len(ids)}" for a, ids in ARMS.items()))
    for c in sorted(report):
        r = report[c]
        print(f"{c} arm={r['arm']} valid={r['valid']} why={r['why']} loadavg={r['loadavg_mean']} "
              f"util={r['util_mean']} qw={r['qw']} diverged_prompts={r['diverged_prompts']} "
              f"counters={r['counters']} own={r['own_seen']} foreign={r['foreign_seen']}")
    if div_cells:
        print("VERDICT: DIVERGENCE-REPRODUCED")
        for c, r in div_cells:
            i = r["diverged_prompts"][0]
            d = json.load(open(os.path.join(outdir, c + ".json")))
            got = d["rows"][i]["out_ids"]
            j, exp_tok, got_tok = first_token_diff(refs[i], got)
            print(f"  {c}: first divergence prompt={i} token_index={j} expected={exp_tok} got={got_tok} "
                  f"counters={r['counters']} routing={r['routing']}")
            print(f"    out_sha[{c}]={r['out_sha']}")
            for mate in ARMS[r["arm"]]:
                if mate != c and report.get(mate):
                    print(f"    out_sha[{mate}]={report[mate]['out_sha']}")
            print(f"    loadavg_mean={r['loadavg_mean']} util_mean={r['util_mean']} "
                  f"own={r['own_seen']} foreign={r['foreign_seen']}")
        print("  REPEAT cell pre-authorized in same arm (flagged REPEAT, not counted in n).")
        exit_code = 4 if invalid else 0
    else:
        print("VERDICT: CONTENTION-SAFE (bounded; no divergence observed)")
        for a, ids in ARMS.items():
            n = sum(1 for c in ids if report.get(c, {}).get("valid"))
            ub = cp_upper(n, 0)
            print(f"  arm {a}: 0/{n} divergent cells; one-sided 95% CP upper bound on per-cell divergence p = {ub:.3f}"
                  if ub is not None else f"  arm {a}: no valid cells")
        n_all = sum(1 for c in report if report[c]["valid"])
        ub = cp_upper(n_all, 0)
        print(f"  pooled: 0/{n_all}; 95% CP upper bound p = {ub:.3f}" if ub is not None else "  pooled: none")
        print("  Claim limit: 'no divergence observed in n cells under these manipulations' - never 'deterministic'.")
        exit_code = 4 if invalid else 0
    if invalid:
        print("invalid/flagged cells (excluded from verdict counts, per PREREG):")
        for c, why in sorted(invalid.items()):
            print(f"  {c}: {why}")
    print("Timing descriptive only (no perf claim):")
    for c in sorted(report):
        d = json.load(open(os.path.join(outdir, c + ".json")))
        dec = [r.get("decode_tok_s") for r in d.get("rows", [])
               if isinstance(r.get("decode_tok_s"), (int, float))]
        if dec:
            print(f"  {c} ({report[c]['arm']}): mean decode {sum(dec)/len(dec):.2f} tok/s")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
