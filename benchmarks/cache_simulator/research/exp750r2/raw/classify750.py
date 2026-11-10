#!/usr/bin/env python3
"""exp750 classifier. Usage:
  classify750.py OUT REFJSON          full classification; last line `VERDICT750 <D1>|<D2>|<D3>|<GQ>|<GM> [flags]`
  classify750.py OUT --list-reruns    print (stdout, one per line, nothing else) the original cell ids that are
                                      FOREIGN / TIMED-DRIFT / TIMER-INVALID and so need one rerun as `<id>_x`

Implements the exp750 PREREG gates G-Q, G-T, G-V, G-M, G-F, the _x replacement rule, decisions D1/D2/D3, the
link ratio D(S0)/D(S1) and the noise floor. cells750.json is read from the parent of OUT (the run dir, as in
exp749); if it is not there, the copy next to this script is used. Inputs per cell id (and its _x variant):
OUT/<id>.json, OUT/<id>.env, OUT/<id>.json.prov.json (engine F/P arms); plus OUT/monitor.csv, OUT/precell.csv
and OUT/rc.csv in the exact exp749 formats (`ts,cell,0, MiB0;1, MiB1;,ollama` for monitor.csv). Fail closed:
any missing or malformed input yields INCOMPLETE / exclusion, never a pass.
"""
import json, re, statistics, sys
from pathlib import Path

ARMS = ("R1", "S1", "S0", "P2", "K2", "C2", "H2")
GQ_ARMS = ("R1", "S1", "S0", "P2", "K2")  # C2 descriptive, H2 not quality-gated (PREREG G-Q)
BLOCKS = (1, 2, 3)
FIX749 = "/moei-fix749/"
FIX740 = "/moei-fix740/"
UNPATCHED = "/moei-engine/"
FOREIGN_SLACK_MIB = 512


# --- per-row / per-cell pure rules -------------------------------------------------------------

def rows_key(cell):
    """[(out_ids, top16_ids, top16_vals)] per prompt row of a loaded cell JSON."""
    return [(r["out_ids"], r["top16_ids"], r["top16_vals"]) for r in cell["rows"]]


def quality_matches(cell, ref):
    """Number of prompts whose (out_ids, top16_ids, top16_vals) equal the reference rows, or None if the
    cell/reference rows are missing or malformed."""
    try:
        rows = rows_key(cell)
    except (KeyError, TypeError, AttributeError):
        return None
    if ref is None or len(rows) != len(ref):
        return None
    return sum(1 for a, b in zip(rows, ref) if a == b)


def timed_identity(cell):
    """G-T: True iff every timed rep's out_ids_64 equals its row's quality-pass out_ids. None if the timed
    data is missing/malformed (fail closed)."""
    try:
        rows = cell["rows"]
        if not rows:
            return None
        for r in rows:
            reps = r["timed"]
            if not reps:
                return None
            for rep in reps:
                if rep["out_ids_64"] != r["out_ids"]:
                    return False
        return True
    except (KeyError, TypeError, AttributeError):
        return None


def timer_sane(cell):
    """G-V: True iff every timed rep has t64 > t1 > 0. None if the timed data is missing/malformed."""
    try:
        rows = cell["rows"]
        if not rows:
            return None
        for r in rows:
            reps = r["timed"]
            if not reps:
                return None
            for rep in reps:
                t1, t64 = float(rep["t1_s"]), float(rep["t64_s"])
                if not (t64 > t1 > 0):
                    return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def prompt_d_ms(row):
    """d_p: median over reps of (t64-t1)/63 in ms/token, with the PREREG literal 63 independent of how
    many tokens a timed run returned (a short run is caught by G-T, not rescaled). None if unusable."""
    try:
        vals = []
        for rep in row["timed"]:
            vals.append((float(rep["t64_s"]) - float(rep["t1_s"])) / 63 * 1000)
        return statistics.median(vals) if vals else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def prompt_e_ms(row):
    """e_p: median over reps of t64/64 in ms/token, with the PREREG literal 64 independent of how many
    tokens a timed run returned. None if unusable."""
    try:
        vals = []
        for rep in row["timed"]:
            vals.append(float(rep["t64_s"]) / 64 * 1000)
        return statistics.median(vals) if vals else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def rep_spread(row):
    """Within-prompt rep spread of the per-rep decode ms/token ((t64-t1)/63): (max-min)/median. None if unusable."""
    try:
        vals = []
        for rep in row["timed"]:
            vals.append((float(rep["t64_s"]) - float(rep["t1_s"])) / 63 * 1000)
        if not vals:
            return None
        med = statistics.median(vals)
        return (max(vals) - min(vals)) / med if med else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def cell_DE(cell):
    """(D, E): median over prompt rows of d_p / e_p. (None, None) if any row is unusable. Raw timed values
    are recomputed here; the harness row d_ms/e_ms fields are not trusted."""
    try:
        rows = cell["rows"]
    except (KeyError, TypeError, AttributeError):
        return None, None
    ds = [prompt_d_ms(r) for r in rows]
    es = [prompt_e_ms(r) for r in rows]
    if not rows or any(v is None for v in ds + es):
        return None, None
    return statistics.median(ds), statistics.median(es)


def cv(vals):
    """Across-block coefficient of variation: sample stdev / mean. None if fewer than 2 values or mean 0."""
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None
    m = statistics.mean(vals)
    return statistics.stdev(vals) / m if m else None


# --- decision rules (ratios within a block; thresholds exactly as PREREG) ----------------------

def decide_d1(qs):
    """D1 q_b = D(K2)/D(P2). Exactly 3 ratios (one per block) required, else INCOMPLETE."""
    if len(qs) != 3:
        return "INCOMPLETE"
    if all(q >= 1.10 for q in qs):
        return "FIX-FASTER"
    if all(q <= 0.91 for q in qs):
        return "WORKAROUND-FASTER"
    if all(0.95 <= q <= 1.05 for q in qs):
        return "EQUIVALENT"
    return "MIXED"


def decide_d2(ss):
    """D2 s_b = D(S1)/D(R1). Exactly 3 ratios (one per block) required, else INCOMPLETE."""
    if len(ss) != 3:
        return "INCOMPLETE"
    if all(0.95 <= s <= 1.05 for s in ss):
        return "NOREGRESS-T"
    if all(s > 1.05 for s in ss):
        return "REGRESS-T"
    if all(s < 0.95 for s in ss):
        return "FASTER-T"
    return "UNRESOLVED-T"


def decide_d3(us):
    """D3 u_b = D(S1)/D(P2). Exactly 3 ratios (one per block) required, else INCOMPLETE."""
    if len(us) != 3:
        return "INCOMPLETE"
    if all(u >= 1.10 for u in us):
        return "TWO-GPU-FASTER"
    if all(u <= 0.91 for u in us):
        return "TWO-GPU-SLOWER"
    return "NEUTRAL/MIXED"


# --- monitor.csv / precell.csv (exact exp749 formats) -------------------------------------------

def parse_gpu_mem(text):
    """'0, 123;1, 456;' -> {0: 123, 1: 456}, or None if any non-empty segment is malformed."""
    mem = {}
    for seg in text.split(";"):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(r"^(\d+),\s*(-?\d+)$", seg)
        if not m:
            return None
        mem[int(m.group(1))] = int(m.group(2))
    return mem or None


def parse_monitor_line(line):
    """'ts,cell,0, MiB0;1, MiB1;,ollama' -> (cell, {gpu: MiB}, ollama) or None if malformed."""
    m = re.match(r"^[^,]+,([^,]+),(.+),(-?\d+)\s*$", line.rstrip("\n"))
    if not m:
        return None
    mem = parse_gpu_mem(m.group(2))
    if mem is None:
        return None
    return m.group(1), mem, int(m.group(3))


def parse_precell_line(line):
    """'cell,0, MiB0;1, MiB1;,ollama' -> (cell, {gpu: MiB}, ollama) or None if malformed."""
    m = re.match(r"^([^,]+),(.+),(-?\d+)\s*$", line.rstrip("\n"))
    if not m:
        return None
    mem = parse_gpu_mem(m.group(2))
    if mem is None:
        return None
    return m.group(1), mem, int(m.group(3))


def read_monitor(out):
    """({cell: [(mem, oll)]}, [malformed lines])."""
    samples, bad = {}, []
    p = out / "monitor.csv"
    if p.exists():
        for l in open(p, errors="replace"):
            if not l.strip():
                continue
            r = parse_monitor_line(l)
            if r is None:
                bad.append(l.rstrip("\n"))
            else:
                samples.setdefault(r[0], []).append((r[1], r[2]))
    return samples, bad


def read_precell(out):
    """({cell: mem}, [malformed lines])."""
    pre, bad = {}, []
    p = out / "precell.csv"
    if p.exists():
        for l in open(p, errors="replace"):
            if not l.strip():
                continue
            r = parse_precell_line(l)
            if r is None:
                bad.append(l.rstrip("\n"))
            else:
                pre[r[0]] = r[1]
    return pre, bad


def foreign_status(cid, gpus, samples, pre, monitor_malformed):
    """G-F: 'FOREIGN' if any sample during the cell has ollama >= 1 or a GPU not assigned to the cell
    exceeds its precell memory + 512 MiB; 'CLEAN' if samples+precell exist and neither holds;
    'G-F-UNKNOWN' whenever that cannot be established (no samples, no precell, malformed monitor)."""
    if monitor_malformed:
        return "G-F-UNKNOWN"
    ss = samples.get(cid)
    base = pre.get(cid)
    if not ss or base is None:
        return "G-F-UNKNOWN"
    try:
        assigned = {int(g) for g in str(gpus).split(",")}
    except ValueError:
        return "G-F-UNKNOWN"
    for mem, oll in ss:
        if oll >= 1:
            return "FOREIGN"
        for g, v in mem.items():
            if g not in assigned:
                if g not in base:
                    return "G-F-UNKNOWN"
                if v > base[g] + FOREIGN_SLACK_MIB:
                    return "FOREIGN"
    return "CLEAN"


# --- small readers (exp749-shaped) ----------------------------------------------------------------

def read_env(path):
    """CUDA_LAUNCH_BLOCKING value recorded in a .env file ('' if unset/empty), or None if no file/line."""
    if not path.exists():
        return None
    val = None
    for l in path.read_text(errors="replace").splitlines():
        if l.startswith("CUDA_LAUNCH_BLOCKING="):
            val = l.split("=", 1)[1].strip()
    return val


def read_rc(out):
    rc = {}
    if (out / "rc.csv").exists():
        for l in open(out / "rc.csv", errors="replace"):
            parts = l.strip().split(",")
            if len(parts) >= 2:  # a malformed line leaves the cell without an rc -> not present (fail closed)
                rc[parts[0]] = parts[1].strip()
    return rc


def load_cell(out, cid):
    """Loaded cell JSON dict if it exists and parses with a rows list, else None."""
    p = out / f"{cid}.json"
    if not p.exists():
        return None
    try:
        d = json.load(open(p))
        if not isinstance(d.get("rows"), list):
            return None
        return d
    except (ValueError, TypeError, AttributeError):
        return None


def prov_tree(out, cid):
    """'749', '740', 'other' or None from <id>.json.prov.json (store_so and moe_infinity paths)."""
    p = out / f"{cid}.json.prov.json"
    if not p.exists():
        return None
    try:
        d = json.load(open(p))
        paths = (d["moe_infinity"], d["store_so"])
    except (KeyError, ValueError, TypeError):
        return "other"
    if all(FIX749 in x for x in paths):
        return "749"
    if all(FIX740 in x for x in paths):
        return "740"
    return "other"


def manip(out, cells):
    """G-M: for every cell (original or _x) with a JSON, the .env CUDA_LAUNCH_BLOCKING equals the arm's clb
    (K2 '1', all others '') and the provenance matches the build. For F/P arms BOTH the .prov.json paths
    AND the store_so recorded inside the cell JSON must be under the arm's tree (F -> fix749, P -> fix740);
    any disagreement is MANIP-FAIL. U -> cell store_so under the unpatched tree; H has no .so provenance.
    Fail closed: if no cell (original or _x) has a loadable JSON, MANIP-INCOMPLETE (not MANIP-OK)."""
    bad = []
    seen = False
    for c in cells:
        for cid in (c["id"], c["id"] + "_x"):
            cell = load_cell(out, cid)
            if cell is None:
                continue
            seen = True
            v = read_env(out / f"{cid}.env")
            if v is None or v != c["clb"]:
                bad.append((cid, "env", v))
            if c["build"] == "F":
                if prov_tree(out, cid) != "749":
                    bad.append((cid, "prov", prov_tree(out, cid)))
                so = cell.get("store_so")
                if not (isinstance(so, str) and FIX749 in so):
                    bad.append((cid, "store_so", so))
            if c["build"] == "P":
                if prov_tree(out, cid) != "740":
                    bad.append((cid, "prov", prov_tree(out, cid)))
                so = cell.get("store_so")
                if not (isinstance(so, str) and FIX740 in so):
                    bad.append((cid, "store_so", so))
            if c["build"] == "U":
                so = cell.get("store_so")
                if not (isinstance(so, str) and UNPATCHED in so):
                    bad.append((cid, "store_so", so))
    if bad:
        return "MANIP-FAIL", bad
    return ("MANIP-OK" if seen else "MANIP-INCOMPLETE"), bad


def find_cells(out):
    """cells750.json from the parent of OUT (run dir), else next to this script. None if neither loads."""
    for p in (out.parent / "cells750.json", Path(__file__).resolve().parent / "cells750.json"):
        try:
            cells = json.load(open(p))
            if isinstance(cells, list) and cells:
                return cells
        except (OSError, ValueError, TypeError):
            continue
    return None


def cell_status(out, cid, celldef, rc, samples, pre, mon_bad, ref):
    """Full per-run status dict. clean = present with rc 0, G-T pass (C2 exempt), G-V pass, G-F CLEAN and a
    computable D. needs_rerun = present with rc 0 but FOREIGN/G-F-UNKNOWN, TIMED-DRIFT or TIMER-INVALID."""
    cell = load_cell(out, cid)
    st = {"id": cid, "arm": celldef["arm"], "block": celldef["block"], "cell": cell,
          "rc": rc.get(cid), "present": cell is not None and rc.get(cid) == "0"}
    st["quality"] = quality_matches(cell, ref) if cell is not None else None
    st["timed_ok"] = (True if celldef["arm"] == "C2" else timed_identity(cell)) if cell is not None else None
    st["timer_ok"] = timer_sane(cell) if cell is not None else None
    st["foreign"] = foreign_status(cid, celldef["gpus"], samples, pre, mon_bad)
    st["D"], st["E"] = cell_DE(cell) if cell is not None else (None, None)
    st["clean"] = bool(st["present"] and st["timed_ok"] is True and st["timer_ok"] is True
                       and st["foreign"] == "CLEAN" and st["D"] is not None)
    st["needs_rerun"] = bool(st["present"] and not st["clean"] and (
        st["foreign"] in ("FOREIGN", "G-F-UNKNOWN") or st["timed_ok"] is not True
        or st["timer_ok"] is not True))
    return st


def gather(out, cells, ref):
    """Per original id: {'orig': status, 'x': status, 'eff': status}. The _x run replaces the original only
    if it is itself clean (and, for G-Q arms, quality-clean) and the original needed a rerun or produced no
    usable JSON/rc (not present); such a clean _x is then the cell of record for its arm/block."""
    rc = read_rc(out)
    samples, mon_bad = read_monitor(out)
    pre, pre_bad = read_precell(out)
    res = {}
    for c in cells:
        orig = cell_status(out, c["id"], c, rc, samples, pre, mon_bad, ref)
        x = cell_status(out, c["id"] + "_x", c, rc, samples, pre, mon_bad, ref)
        x_clean = x["clean"] and (c["arm"] not in GQ_ARMS
                                  or (ref is not None and x["quality"] == len(ref)))
        eff = x if ((orig["needs_rerun"] or not orig["present"]) and x_clean) else orig
        res[c["id"]] = {"def": c, "orig": orig, "x": x, "eff": eff, "replaced": eff is x}
    return res, mon_bad, pre_bad


def list_reruns(out, cells):
    """Original ids that are FOREIGN / TIMED-DRIFT / TIMER-INVALID (incl. G-F-UNKNOWN and missing timed
    data, fail closed). No reference needed: G-T/G-V/G-F do not use it."""
    got, _, _ = gather(out, cells, None)
    return [cid for cid, g in got.items() if g["orig"]["needs_rerun"]]


def quality_fail_arms(got, ref):
    """G-Q arms with any evaluable cell (present with rc 0) failing to match the reference on all prompts.
    A cell whose quality cannot be evaluated (malformed rows) also fails its arm. PREREG Amendment A2: every
    cell that ran (original AND _x) is judged, whether or not it was replaced for timing -- replacement is a
    timing-exclusion device only; a quality mismatch anywhere in a G-Q arm is evidence against the fix."""
    fail = set()
    if ref is None:
        return fail
    for g in got.values():
        if g["def"]["arm"] not in GQ_ARMS:
            continue
        judged = (g["orig"], g["x"])  # PREREG A2 (coordinator): every cell that ran is judged, replaced or not
        for st in judged:
            if st["present"] and st["quality"] != len(ref):
                fail.add(g["def"]["arm"])
    return fail


def decision(decide, num_arm, den_arm, effD, qfail, gm):
    """VOID on MANIP-FAIL or a QUALITY-FAIL involved arm; INCOMPLETE on MANIP-INCOMPLETE (no evidence is not a
    manipulation failure; coordinator fix, fix round 1) or without a clean cell for each involved arm in all 3
    blocks; else the ratio rule over per-block D ratios. Returns (token, ratios)."""
    if gm == "MANIP-INCOMPLETE":
        return "INCOMPLETE", []
    if gm != "MANIP-OK" or num_arm in qfail or den_arm in qfail:
        return "VOID", []
    ratios = []
    for b in BLOCKS:
        n, d = effD.get((num_arm, b)), effD.get((den_arm, b))
        if n is None or d is None:
            return "INCOMPLETE", ratios
        ratios.append(n / d)
    return decide(ratios), ratios


def main(argv):
    if len(argv) < 2:
        print("usage: classify750.py OUT [REFJSON | --list-reruns]", file=sys.stderr)
        return 2
    out = Path(argv[1])
    want_reruns = "--list-reruns" in argv[2:]
    cells = find_cells(out)
    if cells is None:
        print("classify750: cells750.json not found (parent of OUT or next to script)", file=sys.stderr)
        if not want_reruns:
            print("VERDICT750 INCOMPLETE|INCOMPLETE|INCOMPLETE|INCOMPLETE|INCOMPLETE flags: NO-CELLS750")
        return 0
    if want_reruns:
        for cid in list_reruns(out, cells):
            print(cid)
        return 0
    ref = None
    if len(argv) >= 3:
        try:
            ref = rows_key(json.load(open(argv[2])))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            print(f"reference unreadable: {e!r}")
    if ref is None:
        print("reference: MISSING -> G-Q cannot pass, decisions fail closed")
    got, mon_bad, pre_bad = gather(out, cells, ref)
    gm, bad = manip(out, cells)
    qfail = quality_fail_arms(got, ref)
    effD, effE, flags = {}, {}, []
    for cid, g in got.items():
        o, e = g["orig"], g["eff"]
        print(f"{cid}: present={o['present']} rc={o['rc']} quality={o['quality']} timed_ok={o['timed_ok']} "
              f"timer_ok={o['timer_ok']} foreign={o['foreign']} D={o['D']} E={o['E']} clean={o['clean']}"
              + (f" REPLACED-BY {cid}_x (D={e['D']})" if g["replaced"] else "")
              + (f" x: present={g['x']['present']} clean={g['x']['clean']}" if g["x"]["present"] else ""))
        if e["clean"]:
            effD[(e["arm"], e["block"])] = e["D"]
            effE[(e["arm"], e["block"])] = e["E"]
        elif o["present"]:
            why = ("FOREIGN" if o["foreign"] != "CLEAN" else
                   "TIMED-DRIFT" if o["timed_ok"] is not True else
                   "TIMER-INVALID" if o["timer_ok"] is not True else "UNCLEAN")
            flags.append(f"{e['arm']}:EXCLUDED({cid}:{why})")
        else:
            flags.append(f"{g['def']['arm']}:INCOMPLETE({cid}:MISSING)")
    for arm in ARMS:
        have = [effD.get((arm, b)) for b in BLOCKS]
        cs = [g["eff"]["cell"] for g in got.values()
              if g["def"]["arm"] == arm and g["eff"]["clean"] and g["eff"]["cell"] is not None]
        spreads = [rep_spread(r) for c in cs for r in c["rows"]]
        spreads = [s for s in spreads if s is not None]
        print(f"arm {arm}: D per block={have} E per block={[effE.get((arm, b)) for b in BLOCKS]} "
              f"CV(D)={cv(have)} median-rep-spread={statistics.median(spreads) if spreads else None}")
    link = []
    for b in BLOCKS:
        s0, s1 = effD.get(("S0", b)), effD.get(("S1", b))
        link.append(s0 / s1 if (s0 is not None and s1 is not None) else None)
    print(f"link ratio D(S0)/D(S1) per block: {link}")
    d1, q = decision(decide_d1, "K2", "P2", effD, qfail, gm)
    d2, s = decision(decide_d2, "S1", "R1", effD, qfail, gm)
    d3, u = decision(decide_d3, "S1", "P2", effD, qfail, gm)
    if ref is None:  # G-Q unknowable without the reference: fail closed, never a timing verdict
        d1 = d2 = d3 = "INCOMPLETE"
    print(f"D1 q=D(K2)/D(P2) per block: {q} -> {d1}")
    print(f"D2 s=D(S1)/D(R1) per block: {s} -> {d2}")
    print(f"D3 u=D(S1)/D(P2) per block: {u} -> {d3}")
    r1cv = cv([effD.get(("R1", b)) for b in BLOCKS])
    print(f"noise floor: R1 across-block CV(D)={r1cv}")
    if r1cv is not None and r1cv > 0.05:
        flags.append("NOISY")
        print("R1 CV > 5% -> all verdicts flagged NOISY (verdict text kept)")
    c2 = [g for g in got.values() if g["def"]["arm"] == "C2"]
    if ref is not None and len(c2) == 3 and all(
            g["eff"]["present"] and g["eff"]["quality"] == len(ref) for g in c2):
        flags.append("C2-UNEXPECTED-CLEAN")
    gq_missing = any(g["def"]["arm"] in GQ_ARMS and not g["orig"]["present"] and not g["x"]["present"]
                     for g in got.values())
    gq = (f"QUALITY-FAIL({','.join(sorted(qfail))})" if qfail
          else "INCOMPLETE" if (ref is None or gq_missing) else "PASS")
    if mon_bad:
        print(f"malformed monitor.csv lines ({len(mon_bad)}): {mon_bad}")
    if pre_bad:
        print(f"malformed precell.csv lines ({len(pre_bad)}): {pre_bad}")
    print(f"G-Q: {gq}  G-M: {gm} {bad if bad else ''}".rstrip())
    print(f"VERDICT750 {d1}|{d2}|{d3}|{gq}|{gm}" + (f" flags: {' '.join(flags)}" if flags else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
