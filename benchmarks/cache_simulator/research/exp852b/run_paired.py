#!/usr/bin/env python3
"""exp852b: shared-state N-way metadata PAYOFF on a BUSY host — paired, interleaved, fresh-process
timing of shared metadata views vs per-key base (successor of exp852; H3' of exp718).

Sealed deps reused read-only (sealed_deps.sha256, byte-identical copy of exp852's). This experiment
writes only its own dir. Frozen design in PREREG.md (sha recorded at runtime into every output).

Modes:
  run_paired.py                 real run (fresh)
  run_paired.py --resume        one resume of an interrupted real run (keeps completed groups)
  SMOKE=1 run_paired.py         disclosed smoke, never a result
  run_paired.py --worker POLICY CAP STREAM LIMIT    one timed replay in this fresh interpreter
"""

import csv
import gc
import hashlib
import json
import math
import multiprocessing
import os
import platform
import random
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

t0 = time.time()
D = Path(__file__).resolve().parent
HOME = Path.home()
REPO = HOME / "warp-work/moei-granite3b"
RESEARCH = REPO / "benchmarks/cache_simulator/research"
sys.path.insert(0, str(REPO))
PY = sys.executable

# ------------------------------------------------------- frozen design constants (PREREG)
CAPS = [256, 1024, 4096, 262144]
OVERLAP_CAPS = [256, 1024, 4096]
FAMILIES = [("costfit", "shared_costfit"), ("costfit3", "shared_costfit3")]
POLICIES = ["costfit", "costfit3", "shared_costfit", "shared_costfit3"]
# timed arms per block: the 4 policies + an A/A control (a second, independent costfit3 process)
ARMS = {"costfit": "costfit", "costfit3": "costfit3", "shared_costfit": "shared_costfit",
        "shared_costfit3": "shared_costfit3", "costfit3_AA": "costfit3"}
STREAMS = {
    "qwen30b": REPO / "data/belady/stream_qwen30b.pt",
    "granite": REPO / "benchmarks/cache_simulator/data/handcrafted8-greedy512/belady/stream_granite3b.pt",
}
GROUPS = [(s, c) for s in STREAMS for c in CAPS]  # frozen order: qwen30b caps, then granite caps
N_GROUPS = len(GROUPS)
K_BLOCKS = 12                      # set by the pilot rule below BEFORE freeze; frozen
SEED = 852002
WALL_BUDGET_S = 30 * 3600          # per attempt; re-timed from the S13 pilot (smoke r4: 459 s/block on
                                   # granite|256, projected ~22.9 h for 8 groups x K=12); was 16 h
BUDGET_MARGIN = 0.85               # S13: projected run time must be <= 0.85 x WALL_BUDGET_S
TASKPOLICY = "/usr/sbin/taskpolicy"
P_SHARE_MAX = 0.01                 # V4: timed rows must run on E-cores (rusage V6 P-share)
PILOT_GROUP = ("granite", 256)
PILOT_K = 6
PILOT_SD_RULE = 0.12               # pilot sd_log(R3 cpu) > 0.12 -> K = 20, else K = 12 (Jean B-note)
WORKER_TIMEOUT_S = 1800
WORKER_RETRIES = 1                 # one retry of a failed worker process, recorded
ALPHA_UP = 0.05                    # one-sided upper bound per group (intersection-union, no correction)
ALPHA_REJECT = 0.05 / N_GROUPS     # one-sided lower bound per group, Bonferroni over 8 groups
AA_BAND = 1.05                     # A/A Bonferroni interval must not lie wholly outside [1/1.05, 1.05]
AA_MAX_SD_LOG = 0.15               # A/A dispersion cap (Cable B4, folded by Jean)
STRUCT_DRIFT = 0.05
TERMINAL_DRIFT = 0.10
CEILING_MARGIN = 1.05
PAYOFF_CONFIRMED = 1.10
PAYOFF_MARGINAL = 1.35
SMOKE_LIMIT = 150_000
PRIMARY = "cpu_s"                  # getrusage(RUSAGE_SELF) user+sys over the replay window
SECONDARY = "wall_s"               # perf_counter over the same window
LINEAGE = {
    "exp852_PREREG.md": HOME / "warp-work/exp852-moei-shared-payoff/PREREG.md",
    "exp852_run_payoff.py": HOME / "warp-work/exp852-moei-shared-payoff/run_payoff.py",
    "exp852_ADJUDICATION.md": HOME / "warp-work/exp852-moei-shared-payoff/"
                              "ADJUDICATION-20261115T0140Z-exp852-crash2-peer-reap-no-relaunch.md",
    "exp718_PREREG.md": HOME / "warp-work/exp718-moei-shared-econ/PREREG.md",
    "exp718-econ.json": HOME / "warp-work/exp718-moei-shared-econ/exp718-econ.json",
}
ROWS = D / "rows.jsonl"
GROUPS_F = D / "groups.jsonl"
STATUS = D / "status.json"
RESULT = D / "exp852b-paired.json"


def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_sealed_deps():
    deps = {}
    for line in (D / "sealed_deps.sha256").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sha, path = line.split()
        p = Path(path)
        if not p.is_absolute():
            p = REPO / path
        deps[p.name] = (p, sha)
    return deps


def assert_sealed(deps=None):
    deps = deps if deps is not None else load_sealed_deps()
    for label, (p, sha) in deps.items():
        got = sha256_file(p)
        if got != sha:
            raise RuntimeError(f"SEALED DRIFT {label}: {got} != {sha}")
    return deps


import benchmarks.cache_simulator.research.census_shared_costfit as CEN  # noqa: E402
from benchmarks.cache_simulator.policies import build_policy  # noqa: E402
from benchmarks.cache_simulator.research.run_policies_real import (  # noqa: E402
    geometry_kwargs,
    load_accesses,
)


def hb(msg):
    print(f"[{time.time() - t0:7.0f}s {utc()}] {msg}", flush=True)


def append_jsonl(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path):
    if not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_json_atomic(path, obj):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True))
    os.replace(tmp, path)


# ------------------------------------------------------- Student t (no scipy in the venv)
def _betacf(a, b, x):
    MAXIT, EPS, FPMIN = 400, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
        c = 1.0 + aa / c
        c = c if abs(c) > FPMIN else FPMIN
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
        c = 1.0 + aa / c
        c = c if abs(c) > FPMIN else FPMIN
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def _betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    bt = math.exp(lbt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    x = df / (df + t * t)
    tail = 0.5 * _betai(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


def t_ppf(p, df):
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def paired_stats(base_times, shared_times):
    """Paired ratio stats over blocks: geometric mean, one-sided bounds on the log scale."""
    logs = [math.log(s / b) for b, s in zip(base_times, shared_times)]
    k = len(logs)
    if k < 2:
        return None
    m = statistics.fmean(logs)
    sd = statistics.stdev(logs)
    se = sd / math.sqrt(k)
    tu = t_ppf(1 - ALPHA_UP, k - 1)
    tl = t_ppf(1 - ALPHA_REJECT, k - 1)
    return {"k": k, "gmean": math.exp(m), "upper95": math.exp(m + tu * se),
            "lower_bonf": math.exp(m - tl * se), "upper_bonf": math.exp(m + tl * se),
            "sd_log": sd, "t_up": tu, "t_reject": tl,
            "median_ratio": statistics.median([math.exp(x) for x in logs]),
            "min_ratio": math.exp(min(logs)), "max_ratio": math.exp(max(logs))}


# ------------------------------------------------------- measurement primitives
def measure_cell(name, cap, stream_path, repeats, limit=0):
    """Sealed CEN._measure in a fresh spawned process (V1 structural row; unchanged code path)."""
    ctx = multiprocessing.get_context("spawn")
    job = (name, cap, [str(stream_path)], 0, "skip", repeats, limit)
    with ctx.Pool(1) as pool:
        return pool.apply(CEN._measure, (job,))


_V6_FIELDS = {"user_time": 0, "system_time": 1, "qos_background": 20, "instructions": 29,
              "cycles": 30, "runnable_time": 34, "user_ptime": 36, "system_ptime": 37,
              "pinstructions": 38}


def rusage_v6():
    """proc_pid_rusage(RUSAGE_INFO_V6) for this process; layout verified on Mack 15.6 (normal run
    P-share 0.91, `taskpolicy -b` run P-share 0.0 and qos_background == total). Units: mach ticks,
    used only as unit-free shares and as same-unit counters. None if unavailable."""
    try:
        import ctypes
        lib = ctypes.CDLL("/usr/lib/libproc.dylib")
        buf = (ctypes.c_uint64 * 64)()
        if lib.proc_pid_rusage(os.getpid(), 6, ctypes.byref(buf)) != 0:
            return None
        u = list(buf)[2:]  # skip the 16-byte uuid
        return {k: u[i] for k, i in _V6_FIELDS.items()}
    except Exception:
        return None


def worker_main(policy, cap, stream, limit):
    """One timed replay in THIS fresh interpreter. Timing window = sealed _measure's window:
    policy built before the clock starts; clock wraps CEN._replay(fresh policy, accesses)."""
    acc, st = load_accesses([str(STREAMS[stream])], ignore_layers=0, prefill="skip")
    if limit:
        acc = acc[:limit]
    kw = geometry_kwargs(policy, st)
    p = build_policy(policy, cap, **kw)
    gc.collect()
    la0 = os.getloadavg()
    v0 = rusage_v6()
    r0 = resource.getrusage(resource.RUSAGE_SELF)
    th0 = time.thread_time()
    w0 = time.perf_counter()
    CEN._replay(p, acc)
    w1 = time.perf_counter()
    th1 = time.thread_time()
    r1 = resource.getrusage(resource.RUSAGE_SELF)
    v1 = rusage_v6()
    la1 = os.getloadavg()
    n = len(acc)
    cpu_user = r1.ru_utime - r0.ru_utime
    cpu_sys = r1.ru_stime - r0.ru_stime
    v6 = None
    if v0 is not None and v1 is not None:
        d = {k: v1[k] - v0[k] for k in v0}
        tot = d["user_time"] + d["system_time"]
        v6 = {"p_share": ((d["user_ptime"] + d["system_ptime"]) / tot) if tot else None,
              "qos_bg_share": (d["qos_background"] / tot) if tot else None,
              "instructions": d["instructions"], "cycles": d["cycles"],
              "p_instructions": d["pinstructions"], "runnable_ticks": d["runnable_time"]}
    row = {
        "policy": policy, "capacity": cap, "stream": stream, "limit": limit, "accesses": n,
        "hits": p.hits, "misses": p.misses, "hit_rate": p.hit_rate,
        "wall_s": w1 - w0, "cpu_s": cpu_user + cpu_sys, "cpu_user_s": cpu_user, "cpu_sys_s": cpu_sys,
        "thread_cpu_s": th1 - th0, "cpu_minus_thread_s": (cpu_user + cpu_sys) - (th1 - th0),
        "rusage_v6": v6,
        "ns_wall": (w1 - w0) / max(n, 1) * 1e9, "ns_cpu": (cpu_user + cpu_sys) / max(n, 1) * 1e9,
        "nivcsw": r1.ru_nivcsw - r0.ru_nivcsw, "nvcsw": r1.ru_nvcsw - r0.ru_nvcsw,
        "maxrss": r1.ru_maxrss, "loadavg_start": list(la0), "loadavg_end": list(la1),
        "pid": os.getpid(), "t_utc": utc(),
    }
    print("ROW " + json.dumps(row), flush=True)


def run_worker(policy, cap, stream, limit=0):
    """Launch one fresh interpreter (isolated mode) for one timed replay; return its row."""
    # B2 (Jean): every timed worker runs at background QoS -> E-cores only (core type fixed)
    cmd = [TASKPOLICY, "-b", PY, "-I", str(D / "run_paired.py"), "--worker", policy, str(cap),
           stream, str(limit)]
    last_err = None
    for attempt in range(WORKER_RETRIES + 1):
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, timeout=WORKER_TIMEOUT_S,
                                cwd=str(D))
        except subprocess.TimeoutExpired:
            last_err = "timeout"
            continue
        if cp.returncode == 0:
            for line in reversed(cp.stdout.splitlines()):
                if line.startswith("ROW "):
                    row = json.loads(line[4:])
                    row["worker_attempt"] = attempt
                    return row
            last_err = "no ROW line"
        else:
            last_err = f"rc={cp.returncode} stderr_tail={cp.stderr[-400:]!r}"
    raise RuntimeError(f"worker failed {policy}|{cap}|{stream}: {last_err}")


def full_state(p):
    return (p.hits, p.misses, p.hit_rate, p.switches, getattr(p, "choice_switches", None),
            p.choice, p._mass, p._sw_mass, list(p.resident))


def parity_pair(acc, stats, base_name, shared_name, cap):
    a = build_policy(base_name, cap, **geometry_kwargs(base_name, stats))
    b = build_policy(shared_name, cap, **geometry_kwargs(shared_name, stats))
    CEN._replay(a, acc)
    CEN._replay(b, acc)
    ta, tb = full_state(a), full_state(b)
    fields = ("hits", "misses", "hit_rate", "switches", "choice_switches", "choice",
              "_mass", "_sw_mass", "resident_order")
    diff = [f for f, x, y in zip(fields, ta, tb) if x != y]
    return {"base": base_name, "shared": shared_name, "cap": cap, "equal": not diff,
            "diff_fields": diff, "hit_rate": ta[2], "resident_len": len(ta[8])}


def load_anchor(stream):
    path = RESEARCH / f"census_exp675-{stream}.csv"
    rows = {(r["policy"], int(r["capacity"])): r for r in csv.DictReader(path.open())}
    out = {}
    for base, shared in FAMILIES:
        for cap in OVERLAP_CAPS:
            b, s = rows[(base, cap)], rows[(shared, cap)]
            out[f"{base}|{cap}"] = {
                "struct_ratio": int(s["struct_bytes"]) / int(b["struct_bytes"]),
                "terminal_ratio": int(s["terminal_bytes"]) / int(b["terminal_bytes"]),
                "tables_base": int(b["tables"]), "tables_shared": int(s["tables"]),
                "hit_equal": s["hit_rate"] == b["hit_rate"],
            }
    return out


def block_order(group_name, block):
    """Seeded per (group, block) arm order: deterministic, independent of resume position."""
    rng = random.Random(f"{SEED}|{group_name}|{block}")
    arms = list(ARMS)
    rng.shuffle(arms)
    return arms


# ------------------------------------------------------- group analysis (pure; smoke-tested)
TABLES_EXPECTED = {"costfit": 5, "costfit3": 10, "shared_costfit": 1, "shared_costfit3": 1}


def analyze_group(name, v1_rows, rows, k_blocks=K_BLOCKS):
    """v1_rows: {policy: CEN row}; rows: timed rows of this group (attempt-filtered)."""
    g = {"group": name, "v2_ok": True, "v2_fail": [], "accounting_ok": True, "accounting_fail": []}
    by_block = {}
    for r in rows:
        by_block.setdefault(r["block"], {})[r["arm"]] = r
    full = sorted(b for b, arms in by_block.items() if set(arms) == set(ARMS))
    g["blocks_complete"] = len(full)
    g["complete"] = len(full) >= k_blocks
    # V2: each timed row reproduces its V1 anchor cell exactly; arm rows identical across blocks
    ref = {}
    for r in rows:
        pol = ARMS[r["arm"]]
        v1 = v1_rows[pol]
        if r["hit_rate"] != v1["hit_rate"] or r["accesses"] != v1["accesses"]:
            g["v2_ok"] = False
            g["v2_fail"].append(f"{r['arm']}|b{r['block']} hit/acc != V1")
        sig = (r["hits"], r["misses"], r["hit_rate"], r["accesses"])
        if ref.setdefault(pol, sig) != sig:
            g["v2_ok"] = False
            g["v2_fail"].append(f"{r['arm']}|b{r['block']} differs from earlier {pol} row")
    # Cable B1: base-vs-shared equality is a PARITY gate (rung 1), V1 and timed rows
    for b, s in FAMILIES:
        if v1_rows[b]["hit_rate"] != v1_rows[s]["hit_rate"]:
            g["v2_ok"] = False
            g["v2_fail"].append(f"V1 {b}/{s} hit_rate differs")
        if b in ref and s in ref and ref[b] != ref[s]:
            g["v2_ok"] = False
            g["v2_fail"].append(f"timed {b}/{s} (hits, misses, hit_rate, accesses) differ")
    # accounting: tables per policy, family hit equality in V1
    for p in POLICIES:
        if v1_rows[p]["tables"] != TABLES_EXPECTED[p]:
            g["accounting_ok"] = False
            g["accounting_fail"].append(f"{p} tables {v1_rows[p]['tables']}")
    for b, s in FAMILIES:
        if v1_rows[b]["hit_rate"] != v1_rows[s]["hit_rate"]:
            g["accounting_ok"] = False
            g["accounting_fail"].append(f"{b}/{s} V1 hit_rate differs")
    use = full[:k_blocks]
    g["blocks_used"] = use
    for metric in (PRIMARY, SECONDARY):
        fam = {}
        for b, s in FAMILIES:
            fam[s] = paired_stats([by_block[k][b][metric] for k in use],
                                  [by_block[k][s][metric] for k in use])
        fam["AA"] = paired_stats([by_block[k]["costfit3"][metric] for k in use],
                                 [by_block[k]["costfit3_AA"][metric] for k in use])
        g[metric] = fam
    # exp852-style point estimate (median per arm, then ratio) for continuity
    def med(arm, metric):
        return statistics.median(by_block[k][arm][metric] for k in use) if use else None
    g["point"] = {}
    for metric in (PRIMARY, SECONDARY):
        g["point"][metric] = {
            s: (med(s, metric) / med(b, metric)) if use else None for b, s in FAMILIES}
    g["loadavg_rows"] = {"min": min((r["loadavg_start"][0] for r in rows), default=None),
                         "median": statistics.median([r["loadavg_start"][0] for r in rows]) if rows else None,
                         "max": max((r["loadavg_start"][0] for r in rows), default=None)}
    # V4 (Jean B2): every timed row ran on E-cores (rusage V6 P-share <= P_SHARE_MAX)
    shares = [(r.get("rusage_v6") or {}).get("p_share") for r in rows]
    g["p_share_max"] = max((s for s in shares if s is not None), default=None)
    g["p_share_missing"] = sum(s is None for s in shares)
    g["core_ok"] = bool(rows) and g["p_share_missing"] == 0 and g["p_share_max"] <= P_SHARE_MAX
    # diagnostics (reported, never gated)
    g["diag"] = {}
    if use:
        # N2 position report: mean arm position per arm; A/A ratio split by order
        g["diag"]["mean_pos"] = {a: statistics.fmean(by_block[k][a]["pos"] for k in use) for a in ARMS}
        aa_after = [math.log(by_block[k]["costfit3_AA"][PRIMARY] / by_block[k]["costfit3"][PRIMARY])
                    for k in use if by_block[k]["costfit3_AA"]["pos"] > by_block[k]["costfit3"]["pos"]]
        aa_before = [math.log(by_block[k]["costfit3_AA"][PRIMARY] / by_block[k]["costfit3"][PRIMARY])
                     for k in use if by_block[k]["costfit3_AA"]["pos"] < by_block[k]["costfit3"]["pos"]]
        g["diag"]["aa_gmean_when_AA_second"] = math.exp(statistics.fmean(aa_after)) if aa_after else None
        g["diag"]["aa_gmean_when_AA_first"] = math.exp(statistics.fmean(aa_before)) if aa_before else None
        # N4 load-diff diagnostic: corr(log R3 cpu, loadavg(shared) - loadavg(base)) over blocks
        lr = [math.log(by_block[k]["shared_costfit3"][PRIMARY] / by_block[k]["costfit3"][PRIMARY]) for k in use]
        ld = [by_block[k]["shared_costfit3"]["loadavg_start"][0] - by_block[k]["costfit3"]["loadavg_start"][0]
              for k in use]
        try:
            g["diag"]["corr_logR3cpu_loaddiff"] = statistics.correlation(lr, ld)
        except Exception:
            g["diag"]["corr_logR3cpu_loaddiff"] = None
        # same-unit counters: instruction and cycle ratios (load/frequency-robust descriptors)
        for cnt in ("instructions", "cycles"):
            try:
                g["diag"][f"R3_{cnt}_gmean"] = math.exp(statistics.fmean(
                    math.log(by_block[k]["shared_costfit3"]["rusage_v6"][cnt]
                             / by_block[k]["costfit3"]["rusage_v6"][cnt]) for k in use))
            except Exception:
                g["diag"][f"R3_{cnt}_gmean"] = None
        g["diag"]["cpu_minus_thread_s_max"] = max(by_block[k][a].get("cpu_minus_thread_s", 0)
                                                 for k in use for a in ARMS)
    return g


# ------------------------------------------------------- frozen verdict ladder (first hit wins)
def ladder(parity_ok, budget_exceeded, complete, accounting_ok, core_ok, drift_ok, ceiling_ok,
           aa_ok, max_upper, max_lower, trace):
    def v(label, why):
        trace.append(f"{label}: {why}")
        return label
    if not parity_ok:
        return v("PARITY-FAIL", "V3 smoke / V1 full-state parity / V2 anchor consistency")
    if budget_exceeded or not complete:
        return v("INCOMPLETE-BUDGET", f"budget={budget_exceeded} complete={complete}")
    if not accounting_ok:
        return v("ACCOUNTING-FAIL", "tables accounting or V1 family hit equality")
    if not core_ok:
        return v("CORE-POLICY-FAIL", f"a timed row ran with P-core share > {P_SHARE_MAX} or no V6 data")
    if not drift_ok:
        return v("ECONOMICS-DRIFT", f"struct {STRUCT_DRIFT} / terminal {TERMINAL_DRIFT}")
    if not ceiling_ok:
        return v("CEILING-DRIFT", f"struct_ratio(262144) <= {CEILING_MARGIN} x struct_ratio(4096)")
    if not aa_ok:
        return v("NOISE-FLOOR-FAIL", f"A/A Bonferroni interval wholly outside [1/{AA_BAND}, {AA_BAND}] "
                                     f"or A/A sd_log > {AA_MAX_SD_LOG} in some group")
    if max_upper is None or max_lower is None:
        return v("INCOMPLETE-BUDGET", "no R3 stats")
    if max_upper <= PAYOFF_CONFIRMED:
        return v("PAYOFF-CONFIRMED", f"max_g U95(R3) {max_upper:.5f} <= {PAYOFF_CONFIRMED}")
    if max_upper <= PAYOFF_MARGINAL:
        return v("PAYOFF-MARGINAL", f"max_g U95(R3) {max_upper:.5f} <= {PAYOFF_MARGINAL}")
    if max_lower > PAYOFF_MARGINAL:
        return v("PAYOFF-REJECTED", f"max_g Lbonf(R3) {max_lower:.5f} > {PAYOFF_MARGINAL}")
    return v("PAYOFF-INCONCLUSIVE", f"max_g U95 {max_upper:.5f} > {PAYOFF_MARGINAL} and "
                                    f"max_g Lbonf {max_lower:.5f} <= {PAYOFF_MARGINAL}")


def aa_interval_ok(a):
    """Rung 6 per Jean B1 + Cable B4 (folded): NOISE-FLOOR fails when the A/A two-sided
    Bonferroni interval [lower_bonf, upper_bonf] lies wholly outside [1/AA_BAND, AA_BAND], OR the
    A/A dispersion sd_log exceeds AA_MAX_SD_LOG. No point-estimate test on the A/A gmean."""
    return (not (a["upper_bonf"] < 1 / AA_BAND or a["lower_bonf"] > AA_BAND)
            and a["sd_log"] <= AA_MAX_SD_LOG)


CONFIDENT_PASS = ("PAYOFF-CONFIRMED", "PAYOFF-MARGINAL")


def combine_cpu_wall(cpu_verdict, wall_verdict):
    """Cable B5 (as folded by Jean): a CONFIDENT contradiction across 1.35 between the primary
    (cpu) and secondary (wall) R3 ladders -> PAYOFF-INCONCLUSIVE. Only CONFIRMED/MARGINAL vs
    REJECTED counts (both ladders passed every gate incl. A/A to reach a payoff rung). Every other
    disagreement is reported, not adjudicated."""
    if ((cpu_verdict in CONFIDENT_PASS and wall_verdict == "PAYOFF-REJECTED")
            or (cpu_verdict == "PAYOFF-REJECTED" and wall_verdict in CONFIDENT_PASS)):
        return "PAYOFF-INCONCLUSIVE", True
    return cpu_verdict, False


def attempt_gate(prior_attempts, resume):
    """Jean B3 / Cable B2a: attempts counted from attempts.jsonl (written first). Returns the new
    attempt number; raises SystemExit when not allowed. 1 fresh run + 1 resume max."""
    if prior_attempts and not resume:
        raise SystemExit("an attempt already exists (attempts.jsonl): use --resume (one allowed)")
    if resume and not prior_attempts:
        raise SystemExit("--resume with no prior attempt")
    if len(prior_attempts) >= 2:
        raise SystemExit("attempt budget spent (one fresh run + one resume)")
    return len(prior_attempts) + 1


def kept_groups(group_records, prereg_sha):
    """Resume filter: keep only COMPLETE groups recorded under the SAME prereg sha."""
    return {g["group"]: g for g in group_records
            if g.get("prereg_sha256") == prereg_sha and g.get("complete")}


ARTIFACT_FILES = ("PREREG.md", "run_paired.py", "smoke.log", "sealed_deps.sha256")


def check_artifact():
    """Cable B3: verify all 4 frozen files against ARTIFACT.sha256 (names normalized)."""
    artifact = D / "ARTIFACT.sha256"
    if not artifact.exists():
        raise SystemExit("ARTIFACT.sha256 missing: freeze before any real run")
    frozen = {}
    for ln in artifact.read_text().splitlines():
        if ln.strip() and not ln.startswith("#"):
            sha, name = ln.split(maxsplit=1)
            frozen[Path(name.strip()).name] = sha
    live = {f: sha256_file(D / f) for f in ARTIFACT_FILES}
    bad = [f for f in ARTIFACT_FILES if frozen.get(f) != live[f]]
    if bad:
        raise SystemExit(f"frozen sha mismatch vs ARTIFACT.sha256: {bad}")
    return {"ARTIFACT.sha256": sha256_file(artifact), **live}


def family_verdict(groups_done, metric, shared, parity_ok, budget_exceeded, complete,
                   accounting_ok, core_ok, drift_ok, ceiling_ok):
    stats = [g[metric][shared] for g in groups_done if g.get(metric) and g[metric].get(shared)]
    aa = [g[metric]["AA"] for g in groups_done if g.get(metric) and g[metric].get("AA")]
    aa_ok = bool(aa) and len(aa) == len(groups_done) and all(aa_interval_ok(a) for a in aa)
    mu = max((s["upper95"] for s in stats), default=None)
    ml = max((s["lower_bonf"] for s in stats), default=None)
    trace = []
    verdict = ladder(parity_ok=parity_ok, budget_exceeded=budget_exceeded, complete=complete,
                     accounting_ok=accounting_ok, core_ok=core_ok, drift_ok=drift_ok,
                     ceiling_ok=ceiling_ok, aa_ok=aa_ok, max_upper=mu, max_lower=ml, trace=trace)
    return {"verdict": verdict, "trace": trace, "max_upper95": mu, "max_lower_bonf": ml,
            "aa_ok": aa_ok}


def drift_ceiling(v1_all, anchors):
    drift_fail, ceiling_fail = [], []
    for stream in STREAMS:
        for base, shared in FAMILIES:
            for cap in OVERLAP_CAPS:
                b = v1_all[f"{stream}|{cap}"][base]
                s = v1_all[f"{stream}|{cap}"][shared]
                a = anchors[stream][f"{base}|{cap}"]
                sr = s["struct_bytes"] / b["struct_bytes"] if b["struct_bytes"] else None
                tr = s["terminal_bytes"] / b["terminal_bytes"] if b["terminal_bytes"] else None
                if sr is None or abs(sr - a["struct_ratio"]) / a["struct_ratio"] > STRUCT_DRIFT:
                    drift_fail.append(f"{stream}|{base}|{cap} struct {sr} vs {a['struct_ratio']:.4f}")
                if tr is None or abs(tr - a["terminal_ratio"]) / a["terminal_ratio"] > TERMINAL_DRIFT:
                    drift_fail.append(f"{stream}|{base}|{cap} terminal {tr} vs {a['terminal_ratio']:.4f}")
            r4096 = (v1_all[f"{stream}|4096"][shared]["struct_bytes"]
                     / v1_all[f"{stream}|4096"][base]["struct_bytes"])
            r262k = (v1_all[f"{stream}|262144"][shared]["struct_bytes"]
                     / v1_all[f"{stream}|262144"][base]["struct_bytes"])
            if r262k > CEILING_MARGIN * r4096:
                ceiling_fail.append(f"{stream}|{base}: {r262k:.4f} > {CEILING_MARGIN}x {r4096:.4f}")
    return drift_fail, ceiling_fail


# ------------------------------------------------------- smoke (disclosed, never a result)
def smoke():
    out = {"smoke": True, "t": utc()}
    out["S0_sealed_ok"] = bool(assert_sealed())
    try:
        deps = load_sealed_deps()
        k = next(iter(deps))
        deps[k] = (deps[k][0], "0" * 64)
        assert_sealed(deps)
        out["S7_driftbite_ok"] = False
    except RuntimeError:
        out["S7_driftbite_ok"] = True
    anchors = {s: load_anchor(s) for s in STREAMS}
    out["S5_anchors_ok"] = all(anchors[s][f"{ba}|{c}"]["hit_equal"]
                               for s in anchors for ba, _ in FAMILIES for c in OVERLAP_CAPS)
    # S8 Student-t self-test vs published table values
    table = [(0.95, 11, 1.795885), (0.975, 11, 2.200985), (0.95, 5, 2.015048),
             (0.995, 11, 3.105807), (0.99, 20, 2.527977)]
    out["S8_t_table"] = [(p, df, ref, round(t_ppf(p, df), 6)) for p, df, ref in table]
    out["S8_t_ok"] = all(abs(t_ppf(p, df) - ref) < 2e-6 for p, df, ref in table)
    # S8b (Jean N1): independent check of the rejection quantile t(1-0.05/8, 11) = t(0.99375, 11):
    # composite Simpson integration of the t pdf (independent of the incomplete-beta path)
    def t_pdf(x, df):
        c = math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)) / math.sqrt(df * math.pi)
        return c * (1 + x * x / df) ** (-(df + 1) / 2)

    def cdf_simpson(x, df, n=20000):
        h = x / n
        s = t_pdf(0, df) + t_pdf(x, df) + sum((4 if i % 2 else 2) * t_pdf(i * h, df)
                                              for i in range(1, n))
        return 0.5 + s * h / 3
    q = t_ppf(1 - ALPHA_REJECT, 11)
    out["S8b_t_reject_df11"] = round(q, 6)
    out["S8b_simpson_cdf_at_q"] = cdf_simpson(q, 11)
    out["S8b_ok"] = abs(cdf_simpson(q, 11) - (1 - ALPHA_REJECT)) < 1e-7 and abs(
        cdf_simpson(1.795885, 11) - 0.95) < 1e-6
    # S8c A/A gate (Jean B1 + Cable B4): interval wholly outside band, or sd_log > cap
    def aa(lo, hi, sd=0.05):
        return aa_interval_ok({"lower_bonf": lo, "upper_bonf": hi, "sd_log": sd})
    out["S8c_aa_gate_ok"] = (aa(0.97, 1.08) and aa(1.04, 1.10) and aa(0.90, 1.0 / 1.05)
                             and aa(1.05, 1.3)
                             and not aa(1.051, 1.2) and not aa(0.8, 0.95)
                             and aa(0.97, 1.08, sd=AA_MAX_SD_LOG)
                             and not aa(0.97, 1.08, sd=AA_MAX_SD_LOG + 1e-9))
    # S8d CPU/wall confident-contradiction combiner (Cable B5)
    out["S8d_combine_ok"] = (
        combine_cpu_wall("PAYOFF-CONFIRMED", "PAYOFF-REJECTED") == ("PAYOFF-INCONCLUSIVE", True)
        and combine_cpu_wall("PAYOFF-MARGINAL", "PAYOFF-REJECTED") == ("PAYOFF-INCONCLUSIVE", True)
        and combine_cpu_wall("PAYOFF-REJECTED", "PAYOFF-MARGINAL") == ("PAYOFF-INCONCLUSIVE", True)
        and combine_cpu_wall("PAYOFF-REJECTED", "PAYOFF-CONFIRMED") == ("PAYOFF-INCONCLUSIVE", True)
        and combine_cpu_wall("PAYOFF-CONFIRMED", "PAYOFF-MARGINAL") == ("PAYOFF-CONFIRMED", False)
        and combine_cpu_wall("PAYOFF-REJECTED", "PAYOFF-INCONCLUSIVE") == ("PAYOFF-REJECTED", False)
        and combine_cpu_wall("PAYOFF-MARGINAL", "NOISE-FLOOR-FAIL") == ("PAYOFF-MARGINAL", False)
        and combine_cpu_wall("NOISE-FLOOR-FAIL", "PAYOFF-REJECTED") == ("NOISE-FLOOR-FAIL", False))
    # S9 paired-stats self-test: exact constant ratio -> gmean exact, zero-width bounds
    ps = paired_stats([2.0, 3.0, 4.0], [2.2, 3.3, 4.4])
    out["S9_stats_ok"] = (abs(ps["gmean"] - 1.1) < 1e-12 and abs(ps["upper95"] - 1.1) < 1e-12
                          and abs(ps["lower_bonf"] - 1.1) < 1e-12)
    # S6 ladder self-test incl. boundaries
    def v(**kw):
        base = dict(parity_ok=True, budget_exceeded=False, complete=True, accounting_ok=True,
                    core_ok=True, drift_ok=True, ceiling_ok=True, aa_ok=True, max_upper=1.05,
                    max_lower=1.0)
        base.update(kw)
        return ladder(**base, trace=[])
    out["S6_ladder_ok"] = (
        v() == "PAYOFF-CONFIRMED"
        and v(max_upper=PAYOFF_CONFIRMED) == "PAYOFF-CONFIRMED"
        and v(max_upper=PAYOFF_CONFIRMED + 1e-6) == "PAYOFF-MARGINAL"
        and v(max_upper=PAYOFF_MARGINAL) == "PAYOFF-MARGINAL"
        and v(max_upper=PAYOFF_MARGINAL + 1e-6, max_lower=PAYOFF_MARGINAL) == "PAYOFF-INCONCLUSIVE"
        and v(max_upper=1.6, max_lower=PAYOFF_MARGINAL + 1e-6) == "PAYOFF-REJECTED"
        and v(max_upper=2.0, max_lower=1.2) == "PAYOFF-INCONCLUSIVE"
        and v(max_upper=None) == "INCOMPLETE-BUDGET"
        and v(aa_ok=False) == "NOISE-FLOOR-FAIL"
        and v(budget_exceeded=True) == "INCOMPLETE-BUDGET"
        and v(complete=False) == "INCOMPLETE-BUDGET"
        and v(parity_ok=False) == "PARITY-FAIL"
        and v(accounting_ok=False) == "ACCOUNTING-FAIL"
        and v(core_ok=False) == "CORE-POLICY-FAIL"
        and v(core_ok=False, drift_ok=False) == "CORE-POLICY-FAIL"
        and v(drift_ok=False) == "ECONOMICS-DRIFT"
        and v(ceiling_ok=False) == "CEILING-DRIFT")
    # S10 block order deterministic + covers all arms + differs across blocks
    o1, o2 = block_order("qwen30b|256", 0), block_order("qwen30b|256", 0)
    orders = {tuple(block_order("qwen30b|256", b)) for b in range(K_BLOCKS)}
    out["S10_order_ok"] = o1 == o2 and sorted(o1) == sorted(ARMS) and len(orders) > 1
    out["S1_parity_smoke_ok"] = bool(CEN.parity_smoke())
    # S2/S3 worker path at SMOKE_LIMIT: fresh-interpreter rows, hit fields equal sealed _measure
    s2 = []
    for stream in STREAMS:
        for pol in ("costfit3", "shared_costfit3"):
            w = run_worker(pol, 256, stream, SMOKE_LIMIT)
            m = measure_cell(pol, 256, STREAMS[stream], 1, limit=SMOKE_LIMIT)
            s2.append({"stream": stream, "policy": pol, "worker_hit": w["hit_rate"],
                       "measure_hit": m["hit_rate"], "acc": (w["accesses"], m["accesses"]),
                       "cpu_s": round(w["cpu_s"], 4), "wall_s": round(w["wall_s"], 4),
                       "thread_cpu_s": round(w["thread_cpu_s"], 4),
                       "p_share": (w.get("rusage_v6") or {}).get("p_share"),
                       "qos_bg_share": (w.get("rusage_v6") or {}).get("qos_bg_share")})
    out["S2_rows"] = s2
    out["S2_worker_eq_measure"] = all(r["worker_hit"] == r["measure_hit"] and r["acc"][0] == r["acc"][1]
                                      and r["cpu_s"] > 0 and r["wall_s"] > 0 for r in s2)
    out["S2_ecore_ok"] = all(r["p_share"] is not None and r["p_share"] <= P_SHARE_MAX for r in s2)
    # S11 analyze_group end-to-end on a K=2 mini group at SMOKE_LIMIT (real workers, tmp only)
    name = "granite|256"
    v1 = {p: measure_cell(p, 256, STREAMS["granite"], 1, limit=SMOKE_LIMIT) for p in POLICIES}
    rows = []
    for b in range(2):
        for pos, arm in enumerate(block_order(name, b)):
            r = run_worker(ARMS[arm], 256, "granite", SMOKE_LIMIT)
            r.update({"group": name, "block": b, "arm": arm, "pos": pos, "attempt": "smoke"})
            rows.append(r)
    g = analyze_group(name, v1, rows, k_blocks=2)
    out["S11_group"] = {k: g[k] for k in ("blocks_complete", "complete", "v2_ok", "accounting_ok")}
    out["S11_group_ratios"] = {m: {f: (round(g[m][f]["gmean"], 4) if g[m][f] else None)
                                   for f in g[m]} for m in (PRIMARY, SECONDARY)}
    out["S11_core"] = {"core_ok": g["core_ok"], "p_share_max": g["p_share_max"]}
    out["S11_diag"] = g["diag"]
    out["S11_ok"] = g["complete"] and g["v2_ok"] and g["accounting_ok"] and g["core_ok"]
    # S12 persistence round-trip + resume filter + attempt limit (Cable B2c)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.jsonl"
        append_jsonl(p, {"a": 1})
        append_jsonl(p, {"a": 2})
        rt = [r["a"] for r in read_jsonl(p)] == [1, 2]
    recs = [{"group": "qwen30b|256", "prereg_sha256": "S", "complete": True, "attempt": "a1"},
            {"group": "qwen30b|1024", "prereg_sha256": "S", "complete": False, "attempt": "a1"},
            {"group": "granite|256", "prereg_sha256": "OTHER", "complete": True, "attempt": "a0"}]
    filt = sorted(kept_groups(recs, "S")) == ["qwen30b|256"]

    def gate(prior, resume):
        try:
            return attempt_gate(prior, resume)
        except SystemExit:
            return "refused"
    lim = (gate([], False) == 1 and gate([], True) == "refused" and gate(["a1"], False) == "refused"
           and gate(["a1"], True) == 2 and gate(["a1", "a2"], True) == "refused"
           and gate(["a1", "a2"], False) == "refused")
    out["S12_detail"] = {"jsonl_roundtrip": rt, "resume_filter": filt, "attempt_limit": lim}
    out["S12_jsonl_ok"] = rt and filt and lim
    # S14 analyze_group parity hygiene (Cable B1): a base/shared timed mismatch is a V2 (rung 1) fail
    v1f = {p: {"hit_rate": 0.5, "accesses": 10, "tables": TABLES_EXPECTED[p]} for p in POLICIES}
    fake = []
    for b in range(2):
        for pos, arm in enumerate(block_order("t|1", b)):
            hits = 6 if arm == "shared_costfit" else 5
            fake.append({"arm": arm, "block": b, "pos": pos, "hit_rate": 0.5, "accesses": 10,
                         "hits": hits, "misses": 10 - hits, "cpu_s": 1.0, "wall_s": 1.0,
                         "loadavg_start": [1, 1, 1], "rusage_v6": {"p_share": 0.0}})
    gf = analyze_group("t|1", v1f, fake, k_blocks=2)
    out["S14_parity_hygiene_ok"] = (not gf["v2_ok"]) and any("timed costfit/shared_costfit" in x
                                                              for x in gf["v2_fail"])
    # S13 PILOT (smoke data, never a result): PILOT_K blocks of the full-stream PILOT_GROUP on
    # E-cores -> sd_log(R3 cpu) sets K by the pre-declared rule; smoke fails if K_BLOCKS != rule.
    ps_, pc_ = PILOT_GROUP
    pname = f"{ps_}|{pc_}"
    pv1 = {p: measure_cell(p, pc_, STREAMS[ps_], 1) for p in POLICIES}
    prow = []
    tp0 = time.time()
    for b in range(PILOT_K):
        for pos, arm in enumerate(block_order(pname, b)):
            r = run_worker(ARMS[arm], pc_, ps_, 0)
            r.update({"group": pname, "block": b, "arm": arm, "pos": pos, "attempt": "pilot"})
            prow.append(r)
    pg = analyze_group(pname, pv1, prow, k_blocks=PILOT_K)
    sd = pg[PRIMARY]["shared_costfit3"]["sd_log"]
    out["S13_pilot"] = {
        "group": pname, "blocks": PILOT_K, "elapsed_s": round(time.time() - tp0, 1),
        "s_per_block": round((time.time() - tp0) / PILOT_K, 1),
        "sd_log_R3_cpu": sd, "sd_log_R3_wall": pg[SECONDARY]["shared_costfit3"]["sd_log"],
        "sd_log_AA_cpu": pg[PRIMARY]["AA"]["sd_log"],
        "gmean_R3_cpu": pg[PRIMARY]["shared_costfit3"]["gmean"],
        "gmean_R2_cpu": pg[PRIMARY]["shared_costfit"]["gmean"],
        "gmean_AA_cpu": pg[PRIMARY]["AA"]["gmean"],
        "v2_ok": pg["v2_ok"], "core_ok": pg["core_ok"], "p_share_max": pg["p_share_max"],
        "diag": pg["diag"],
        "loadavg": pg["loadavg_rows"],
        "worker_cpu_s_by_arm": {a: round(statistics.median(r["cpu_s"] for r in prow if r["arm"] == a), 3)
                                for a in ARMS},
        "K_rule": 20 if sd > PILOT_SD_RULE else 12,
    }
    # S13b budget projection: scale the pilot's s/block by stream length and per-access CPU cost
    # (S2 rows at equal SMOKE_LIMIT) for each stream; the full run must fit BUDGET_MARGIN x budget.
    lens = {s: len(load_accesses([str(STREAMS[s])], ignore_layers=0, prefill="skip")[0])
            for s in STREAMS}
    cpu150 = {s: statistics.mean(r["cpu_s"] for r in s2 if r["stream"] == s) for s in STREAMS}
    spb = out["S13_pilot"]["s_per_block"]
    per_stream = {s: spb * (lens[s] / lens[ps_]) * (cpu150[s] / cpu150[ps_]) for s in STREAMS}
    projected = sum(K_BLOCKS * per_stream[s] for s, _c in GROUPS)
    out["S13b_budget"] = {"stream_accesses": lens, "cpu_s_at_smoke_limit": cpu150,
                          "s_per_block_by_stream": {s: round(v, 1) for s, v in per_stream.items()},
                          "projected_s": round(projected), "projected_h": round(projected / 3600, 2),
                          "budget_s": WALL_BUDGET_S, "margin": BUDGET_MARGIN}
    out["S13b_budget_ok"] = projected <= BUDGET_MARGIN * WALL_BUDGET_S
    out["S13_ok"] = pg["v2_ok"] and pg["core_ok"] and out["S13_pilot"]["K_rule"] == K_BLOCKS
    keys = ("S0_sealed_ok", "S7_driftbite_ok", "S5_anchors_ok", "S8_t_ok", "S8b_ok",
            "S8c_aa_gate_ok", "S8d_combine_ok", "S9_stats_ok", "S6_ladder_ok", "S10_order_ok",
            "S1_parity_smoke_ok", "S2_worker_eq_measure", "S2_ecore_ok", "S11_ok", "S12_jsonl_ok",
            "S14_parity_hygiene_ok", "S13_ok", "S13b_budget_ok")
    out["failed"] = [k for k in keys if not out[k]]
    out["all_ok"] = not out["failed"]
    return out


# ------------------------------------------------------- real run
def run(resume=False):
    artifact_shas = check_artifact()
    prereg_sha = artifact_shas["PREREG.md"]
    runner_sha = artifact_shas["run_paired.py"]
    # B3 (Jean): attempts are counted from attempts.jsonl (written FIRST, before any work), so an
    # attempt that dies before its first timed row still consumes budget. 1 fresh + 1 resume max.
    prior_attempts = [a.get("attempt") for a in read_jsonl(D / "attempts.jsonl")]
    attempt = f"a{attempt_gate(prior_attempts, resume)}-{utc()}"
    append_jsonl(D / "attempts.jsonl", {"attempt": attempt, "prereg_sha256": prereg_sha,
                                        "runner_sha256": runner_sha, "started_utc": utc(),
                                        "pid": os.getpid(), "loadavg": list(os.getloadavg()),
                                        "resume": resume})
    hb(f"exp852b attempt {attempt} host {platform.platform()} py {sys.version.split()[0]} "
       f"loadavg {os.getloadavg()} pid {os.getpid()}")
    try:
        _run_body(attempt, prereg_sha, runner_sha, artifact_shas)
    except BaseException as e:  # N3 (Jean): leave an INCOMPLETE result on crash, then re-raise
        write_json_atomic(RESULT, {"exp": "exp852b-moei-shared-payoff-paired", "attempt": attempt,
                                   "prereg_sha256": prereg_sha, "runner_sha256": runner_sha,
                                   "verdict": "INCOMPLETE-BUDGET", "crashed": repr(e)[:2000],
                                   "groups_done": [g.get("group") for g in read_jsonl(GROUPS_F)],
                                   "finished_utc": utc(), "elapsed_s": round(time.time() - t0, 1)})
        hb(f"CRASHED: {e!r}; wrote INCOMPLETE result")
        raise


def _run_body(attempt, prereg_sha, runner_sha, artifact_shas):
    deps = assert_sealed()
    hb(f"sealed deps ok ({len(deps)} files)")
    parity_smoke_ok = bool(CEN.parity_smoke())
    hb(f"parity_smoke {parity_smoke_ok}")
    anchors = {s: load_anchor(s) for s in STREAMS}
    done_groups = kept_groups(read_jsonl(GROUPS_F), prereg_sha)
    stream_cache = {}
    meta = {"attempt": attempt, "prereg_sha256": prereg_sha, "runner_sha256": runner_sha,
            "started_utc": utc(), "resumed_groups": sorted(done_groups)}
    append_jsonl(D / "attempt-detail.jsonl", meta | {"loadavg": list(os.getloadavg()),
                                                      "parity_smoke": parity_smoke_ok})
    budget_exceeded = False
    for stream, cap in GROUPS:
        name = f"{stream}|{cap}"
        if name in done_groups:
            hb(f"group {name}: kept from earlier attempt {done_groups[name]['attempt']}")
            continue
        if time.time() - t0 > WALL_BUDGET_S:
            budget_exceeded = True
            hb(f"group {name}: SKIPPED (wall budget)")
            break
        if stream not in stream_cache:
            stream_cache.clear()
            stream_cache[stream] = load_accesses([str(STREAMS[stream])], ignore_layers=0,
                                                 prefill="skip")
        acc, sts = stream_cache[stream]
        hb(f"group {name}: V1 parity + structural rows")
        pairs = [parity_pair(acc, sts, b, s, cap) for b, s in FAMILIES]
        v1 = {p: measure_cell(p, cap, STREAMS[stream], 1) for p in POLICIES}
        rows = []
        for b in range(K_BLOCKS):
            if time.time() - t0 > WALL_BUDGET_S:
                budget_exceeded = True
                break
            for pos, arm in enumerate(block_order(name, b)):
                r = run_worker(ARMS[arm], cap, stream, 0)
                r.update({"group": name, "block": b, "arm": arm, "pos": pos, "attempt": attempt})
                append_jsonl(ROWS, r)
                rows.append(r)
            hb(f"group {name} block {b + 1}/{K_BLOCKS} done "
               f"(load {os.getloadavg()[0]:.2f})")
        g = analyze_group(name, v1, rows)
        g.update({"attempt": attempt, "prereg_sha256": prereg_sha, "runner_sha256": runner_sha,
                  "pairs": pairs, "v1_rows": v1, "parity_ok": all(p["equal"] for p in pairs),
                  "finished_utc": utc()})
        append_jsonl(GROUPS_F, g)
        done_groups[name] = g
        r3 = g[PRIMARY]["shared_costfit3"]
        hb(f"group {name} done complete={g['complete']} v2={g['v2_ok']} parity={g['parity_ok']} "
           f"R3cpu gmean={r3 and round(r3['gmean'], 4)} U95={r3 and round(r3['upper95'], 4)}")
        write_json_atomic(STATUS, {"attempt": attempt, "groups_done": sorted(done_groups),
                                   "t_utc": utc(), "elapsed_s": round(time.time() - t0)})
        if budget_exceeded:
            break
    # ---- adjudicate (frozen ladder) over all persisted complete-or-not groups of this prereg
    groups_done = [done_groups[f"{s}|{c}"] for s, c in GROUPS if f"{s}|{c}" in done_groups]
    complete = len(groups_done) == N_GROUPS and all(g["complete"] for g in groups_done)
    parity_ok = (parity_smoke_ok and all(g["parity_ok"] for g in groups_done)
                 and all(g["v2_ok"] for g in groups_done))
    accounting_ok = all(g["accounting_ok"] for g in groups_done)
    core_ok = bool(groups_done) and all(g["core_ok"] for g in groups_done)
    drift_fail, ceiling_fail = (["incomplete"], ["incomplete"])
    if len(groups_done) == N_GROUPS:
        drift_fail, ceiling_fail = drift_ceiling({g["group"]: g["v1_rows"] for g in groups_done},
                                                 anchors)
    common = dict(parity_ok=parity_ok, budget_exceeded=budget_exceeded, complete=complete,
                  accounting_ok=accounting_ok, core_ok=core_ok, drift_ok=not drift_fail,
                  ceiling_ok=not ceiling_fail)
    primary = family_verdict(groups_done, PRIMARY, "shared_costfit3", **common)
    secondary = {
        "R3_wall": family_verdict(groups_done, SECONDARY, "shared_costfit3", **common),
        "R2_cpu": family_verdict(groups_done, PRIMARY, "shared_costfit", **common),
        "R2_wall": family_verdict(groups_done, SECONDARY, "shared_costfit", **common),
    }
    final_verdict, contradiction = combine_cpu_wall(primary["verdict"], secondary["R3_wall"]["verdict"])
    point = {m: {f: max((g["point"][m][f] for g in groups_done if g["point"][m][f]), default=None)
                 for _, f in FAMILIES} for m in (PRIMARY, SECONDARY)}
    try:
        sealed_post = bool(assert_sealed())
    except RuntimeError as e:
        sealed_post = str(e)
    out = {
        "exp": "exp852b-moei-shared-payoff-paired",
        "attempt": attempt, "prereg_sha256": prereg_sha, "runner_sha256": runner_sha,
        "lineage": {k: sha256_file(p) for k, p in LINEAGE.items()},
        "sealed_deps": {k: v[1] for k, v in deps.items()}, "sealed_post_ok": sealed_post,
        "host": {"platform": platform.platform(), "python": sys.version.split()[0],
                 "torch": __import__("torch").__version__, "ncpu": os.cpu_count()},
        "design": {"caps": CAPS, "arms": ARMS, "streams": list(STREAMS), "k_blocks": K_BLOCKS,
                   "seed": SEED, "alpha_up": ALPHA_UP, "alpha_reject": ALPHA_REJECT,
                   "aa_band": AA_BAND, "aa_max_sd_log": AA_MAX_SD_LOG, "p_share_max": P_SHARE_MAX,
                   "primary": PRIMARY, "secondary": SECONDARY,
                   "wall_budget_s": WALL_BUDGET_S},
        "parity_smoke": parity_smoke_ok, "anchors_stageA": anchors,
        "groups": [{k: v for k, v in g.items() if k not in ("v1_rows",)} for g in groups_done],
        "v1_rows": {g["group"]: g["v1_rows"] for g in groups_done},
        "drift_fail": drift_fail, "ceiling_fail": ceiling_fail,
        "complete": complete, "budget_exceeded": budget_exceeded,
        "verdict": final_verdict, "cpu_wall_contradiction": contradiction,
        "primary": primary, "secondary": secondary,
        "point_exp852_style_max_ratio": point, "artifact_sha256": artifact_shas,
        "rows_jsonl_sha256": sha256_file(ROWS) if ROWS.exists() else None,
        "finished_utc": utc(), "elapsed_s": round(time.time() - t0, 1),
    }
    write_json_atomic(RESULT, out)
    hb(f"wrote {RESULT.name}")
    hb(f"settled verdict={final_verdict} (cpu ladder {primary['verdict']}, wall ladder "
       f"{secondary['R3_wall']['verdict']}, contradiction={contradiction}) trace={primary['trace']}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--worker":
        worker_main(sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5]))
        sys.exit(0)
    if os.environ.get("SMOKE"):
        res = smoke()
        print(json.dumps(res, indent=1))
        sys.exit(0 if res["all_ok"] else 1)
    run(resume="--resume" in sys.argv)
    print("RUN_EXIT=0", flush=True)
