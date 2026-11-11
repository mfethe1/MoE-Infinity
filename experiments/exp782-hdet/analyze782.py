#!/usr/bin/env python3
"""exp782 analyzer — H-vs-RC decode determinism under identical co-tenancy.
Derived from exp760 analyzer A2 (proven, fixture-reviewed). Changes:
- Cells come from cells782.json: {id, arm(Q/C/G/CG), mode(H|RC), stress, gpu}.
- Banner gate is per-mode: H cells must log "exp752 mode=0" (env unset), RC cells
  "exp752 mode=2". Wrong/absent banner = invalid cell.
- TWO anchors: QH1 (quiet H) and QR1 (quiet RC) must BOTH be byte-identical to the
  sealed refs (refs/RC_2.json==RC_3.json, exp760 lineage). Any valid anchor cell
  diverging = ANCHOR-FAIL (exit 2), never a divergence.
- Verdict (rc line): 1 H-UNSTABLE-RC-STABLE; 2 BOTH-UNSTABLE; 3 RC-UNSTABLE-H-STABLE;
  7 BOTH-STABLE (CP bounds printed); 9 DATA-FAIL (missing cells/no valid contended).
Exit codes: rc value; ANCHOR-FAIL exits 2; no-valid-anchor exits 3.
Usage: python3 analyze782.py <out-dir> [--refs refs] [--cells cells782.json]
"""
import json, sys, os, math, re

OWN_PIDS_FILES = ("eng.pid", "col.pid")
MON_MIN_SAMPLES = 3
UTIL_MIN_SAMPLES = 10
GPU_UTIL_MEAN_MIN = 20.0
MODE_BANNER = {"H": "exp752 mode=0", "RC": "exp752 mode=2"}


def load_refs(refdir):
    r2 = json.load(open(os.path.join(refdir, "RC_2.json")))
    r3 = json.load(open(os.path.join(refdir, "RC_3.json")))
    v2 = [r["out_ids"] for r in r2["rows"]]
    v3 = [r["out_ids"] for r in r3["rows"]]
    if v2 != v3:
        raise SystemExit("FATAL: sealed refs RC_2/RC_3 disagree; cannot anchor")
    return v2


def load_cells(path):
    cells = json.load(open(path))
    for c in cells:
        assert set(c) >= {"id", "arm", "mode"}, c
        assert c["arm"] in ("Q", "C", "G", "CG") and c["mode"] in ("H", "RC"), c
    return cells


def cp_upper(n, k, conf=0.95):
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


def col_presence(outdir, cid):
    """v2 presence evidence (smi compute-apps listing broke after 2026-11-10, live-probed):
    col.pid file's first token must equal the pid in col.log's banner line
    'exp757-col pid=X ...'; returns (ok, why, pid)."""
    pidf = os.path.join(outdir, cid + ".col.pid")
    if not os.path.exists(pidf):
        return False, "col-pidfile-missing", None
    toks = [t for t in open(pidf).read().split() if t.isdigit()]
    if not toks:
        return False, "col-pidfile-empty", None
    pid = toks[0]
    logp = os.path.join(outdir, cid + ".col.log")
    try:
        with open(logp, errors="replace") as f:
            m = re.search(r"exp757-col pid=(\d+)", f.read())
    except OSError:
        m = None
    if not m:
        return False, "col-banner-missing", pid
    if m.group(1) != pid:
        return False, "col-banner-pid-mismatch", pid
    return True, "", pid


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "out"
    refdir, cellpath = "refs", "cells782.json"
    if "--refs" in sys.argv:
        refdir = sys.argv[sys.argv.index("--refs") + 1]
    if "--cells" in sys.argv:
        cellpath = sys.argv[sys.argv.index("--cells") + 1]
    refs = load_refs(refdir)
    cells = load_cells(cellpath)
    flagged = set()
    fp = os.path.join(outdir, "FLAGGED")
    if os.path.exists(fp):
        flagged = {l.strip() for l in open(fp) if l.strip()}
    precell = read_precell(outdir)

    report, invalid = {}, {}
    for c in cells:
        cid, arm, mode = c["id"], c["arm"], c["mode"]
        p = os.path.join(outdir, cid + ".json")
        if not os.path.exists(p):
            invalid[cid] = "missing-out"
            report[cid] = {"arm": arm, "mode": mode, "valid": False, "why": ["missing-out"],
                           "diverged_prompts": None}
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
        if any(r.get("out_ids") is None for r in rows):
            reasons.append("missing-out-ids")
        logp = os.path.join(outdir, cid + ".log")
        try:
            with open(logp, errors="replace") as f:
                logtxt = f.read()
            if MODE_BANNER[mode] not in logtxt:
                reasons.append("wrong-mode-banner")
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
        if foreign_seen:
            reasons.append("foreign-app:" + ";".join(sorted(foreign_seen)))
        if arm == "Q":
            if la is not None and la > 4.0:
                reasons.append("q-loadavg>4")
        else:
            if arm in ("C", "CG") and (la is None or la < 8.0):
                reasons.append("manip-fail-cpu(loadavg mean < 8)")
            if arm in ("G", "CG"):
                ok, why, _pid = col_presence(outdir, cid)
                if not ok:
                    reasons.append("manip-fail-gpu(" + why + ")")
                elif util_mean is None or util_mean < GPU_UTIL_MEAN_MIN:
                    reasons.append("manip-fail-gpu(util mean < 20)")
        out_ids = [r.get("out_ids") for r in rows]
        diverged = [i for i, v in enumerate(out_ids) if v is not None and i < len(refs) and v != refs[i]]
        report[cid] = {"arm": arm, "mode": mode, "valid": not reasons, "why": reasons,
                       "loadavg_mean": la, "util_mean": util_mean,
                       "diverged_prompts": diverged,
                       "out_sha": [r.get("out_sha") for r in rows]}
        if reasons:
            invalid[cid] = ";".join(reasons)

    print("== exp782 verdict (analyzer, derived from exp760 A2) ==")
    if invalid:
        print("invalid cells (excluded):")
        for c, why in sorted(invalid.items()):
            print(f"  {c}: {why}")
    # anchors: quiet cells must equal sealed refs
    for cid in ("QH1", "QR1"):
        r = report.get(cid)
        if r is None:
            print(f"VERDICT: NO-VALID-DATA (missing anchor {cid})"); print("rc=9"); return 9
        if r["valid"] and r["diverged_prompts"]:
            print(f"VERDICT: ANCHOR-FAIL ({cid} diverged from sealed refs):", r["diverged_prompts"])
            print("No determinism verdict issued (prereg). Raw data stands.")
            return 2
    anchors = {}
    for mode, cid in (("H", "QH1"), ("RC", "QR1")):
        r = report.get(cid, {})
        if r.get("valid"):
            anchors[mode] = cid
        else:
            print(f"WARN: anchor {cid} invalid ({r.get('why')}); arm {mode} verdict unreliable")
    if not anchors:
        print("VERDICT: NO-VALID-DATA (no valid anchor cell)")
        return 3

    contended = {m: [c["id"] for c in cells if c["mode"] == m and c["arm"] != "Q"] for m in ("H", "RC")}
    validc = {m: [c for c in ids if report.get(c, {}).get("valid")] for m, ids in contended.items()}
    div = {m: [c for c in validc[m] if report[c]["diverged_prompts"]] for m in ("H", "RC")}
    for m in ("H", "RC"):
        n, k = len(validc[m]), len(div[m])
        ub = cp_upper(n, k) if n else None
        print(f"arm {m}: {k}/{n} valid contended cells diverged"
              + (f"; one-sided 95% CP upper bound p = {ub:.3f}" if ub is not None else " (no valid contended cells)"))
    if not validc["H"] or not validc["RC"]:
        print("VERDICT: DATA-FAIL (an arm has no valid contended cells)")
        print("rc=9")
        return 9
    if div["H"] and not div["RC"]:
        rc = 1; msg = "H-UNSTABLE-RC-STABLE: legacy host-callback path diverges under load; event-poll (RC) byte-stable"
    elif div["H"] and div["RC"]:
        rc = 2; msg = "BOTH-UNSTABLE: divergence is not mode-specific under these manipulations"
    elif not div["H"] and div["RC"]:
        rc = 3; msg = "RC-UNSTABLE-H-STABLE (unexpected; contradicts exp760 0/10)"
    else:
        rc = 7; msg = "BOTH-STABLE (bounded; no divergence observed in either arm)"
    print(f"VERDICT: {msg}")
    print("rc=%d" % rc)
    for c in sorted(report):
        r = report[c]
        print(f"{c} arm={r['arm']} mode={r['mode']} valid={r['valid']} why={r['why']} "
              f"diverged={r['diverged_prompts']} loadavg={r.get('loadavg_mean')} util={r.get('util_mean')}")
    if div["H"] or div["RC"]:
        for c in div["H"] + div["RC"]:
            i = report[c]["diverged_prompts"][0]
            d = json.load(open(os.path.join(outdir, c + ".json")))
            got = d["rows"][i]["out_ids"]
            j, exp_tok, got_tok = first_token_diff(refs[i], got)
            print(f"  {c}: first divergence prompt={i} token_index={j} expected={exp_tok} got={got_tok}")
            print(f"    out_sha={report[c]['out_sha']}")
    print("Claim limit: 'no divergence observed in n cells under these manipulations' - never 'deterministic'.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
