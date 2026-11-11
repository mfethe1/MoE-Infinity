#!/usr/bin/env python3
"""fixtures770.py — battery for analyze770.py. Builds synthetic run dirs under
a temp base, runs the frozen analyzer, asserts rc + key line per branch."""
import os, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze770.py")
W0, W1 = 100.0, 160.0  # window span

def mk_arm(d, arm, W, cpu_lgc_spec, buckets, tidrows_scale=1.0):
    """cpu_lgc_spec: (ut0,st0,ut1,st1) ticks for process-level oscsv.
    buckets: list of (name, d_ticks) — linear ramp across window."""
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    rows = []
    for i in range(6):
        rows.append({"t_1tok_s": 0.5, "t_full_s": W / 6.0,
                     "win_full": [W0 + i * 10.0, W0 + i * 10.0 + 10.0],
                     "decode_tok_s": 12.0})
    import json
    json.dump({"rows": rows}, open(os.path.join(d, "out", arm + ".json"), "w"))
    ut0, st0, ut1, st1 = cpu_lgc_spec
    with open(os.path.join(d, "out", arm + ".oscsv"), "w") as f:
        f.write("# clk_tck=100\n")
        f.write("t,utime_t,stime_t,threads,minflt,majflt,rss_kb,vol,nonvol,read_kb,write_kb\n")
        t = W0 - 5.0
        n = 0
        while t <= W1 + 5.0:
            frac = 0.0 if t < W0 else (1.0 if t > W1 else (t - W0) / (W1 - W0))
            ut = ut0 + int((ut1 - ut0) * frac)
            st = st0 + int((st1 - st0) * frac)
            inwin = 1 if W0 <= t <= W1 else 0
            f.write(f"{t:.3f},{ut},{st},54,1000,5,15320000,1000,50,1024,512\n")
            t += 0.05
            n += inwin
    with open(os.path.join(d, "out", arm + ".tidcsv"), "w") as f:
        f.write("# clk_tck=100 pid=4242\n")
        f.write("t,bucket,nthreads,utime_sum_t,stime_sum_t\n")
        t = W0 - 5.0
        while t <= W1 + 5.0:
            frac = 0.0 if t < W0 else (1.0 if t > W1 else (t - W0) / (W1 - W0))
            if W0 <= t <= W1 or n_row_ok(t):
                for name, dt in buckets:
                    base_ticks = 500
                    v = base_ticks + int(dt * frac)
                    f.write(f"{t:.3f},{name},1,{v},0\n")
            t += 0.05 / max(tidrows_scale, 0.001)

def n_row_ok(t):
    return W0 - 0.1 <= t <= W1 + 0.1

def build(case, src="b7f6ca4d2caa5229698d78deb03b454fc20947dd", **kw):
    d = tempfile.mkdtemp(prefix=f"f770-{case}-")
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    open(os.path.join(d, "out", "SRC_HEAD.txt"), "w").write(src + "\n")
    return d

def run(d):
    r = subprocess.run([sys.executable, AN, d, d], capture_output=True, text=True)
    rc = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="):
            rc = int(ln[3:])
    return rc, r.stdout + r.stderr

CASES = []
def case(name, expect_rc, grep=None):
    CASES.append((name, expect_rc, grep))

# 1 main-bound: Dcpu=1200 ticks=12s; MAIN +9s (75%)
case("main-bound", 1, "MAIN-BOUND")
# 2 threaded-worker: Thread-3 +10s
case("threaded-worker", 2, "THREADED-WORKER")
# 3 pool-unnamed: python3 (non-main comm) +11s
case("pool-unnamed", 3, "POOL-UNNAMED")
# 4 diffuse: three buckets +4s each
case("diffuse", 7, "DIFFUSE")
# 5 no-signal: Dcpu=1.5s
case("no-signal", 5, "NO-SIGNAL")
# 6 reversed: Dcpu=-6s
case("reversed", 8, "REVERSED")
# 7 identify-fail: SRC_HEAD wrong
case("identify-fail", 9, "IDENTIFY-FAIL")
# 8 data-fail: tidcsv missing
case("data-fail", 4, "DATA-FAIL")
# 9 coverage-out: buckets sum 0.2x Dcpu
case("coverage-out", 4, "coverage")

def main():
    results = []
    for name, expect, grep in CASES:
        d = build(name)
        if name == "main-bound":
            mk_arm(d, "OS_LGC", 36, (1000, 500, 2800, 1100), [("MAIN", 800), ("Thread-1", 200), ("python3", 400)])
            mk_arm(d, "OS_SPEC", 43, (1000, 500, 3600, 1400), [("MAIN", 1700), ("Thread-1", 250), ("python3", 450)])
        elif name == "threaded-worker":
            mk_arm(d, "OS_LGC", 36, (1000, 500, 2800, 1100), [("MAIN", 800), ("Thread-3", 100), ("python3", 400)])
            mk_arm(d, "OS_SPEC", 43, (1000, 500, 3600, 1400), [("MAIN", 900), ("Thread-3", 1100), ("python3", 450)])
        elif name == "pool-unnamed":
            mk_arm(d, "OS_LGC", 36, (1000, 500, 2800, 1100), [("MAIN", 800), ("python3", 400)])
            mk_arm(d, "OS_SPEC", 43, (1000, 500, 3600, 1400), [("MAIN", 900), ("python3", 1500)])
        elif name == "diffuse":
            mk_arm(d, "OS_LGC", 36, (1000, 500, 2800, 1100), [("A", 300), ("B", 300), ("C", 300)])
            mk_arm(d, "OS_SPEC", 43, (1000, 500, 3600, 1400), [("A", 700), ("B", 700), ("C", 700)])
        elif name == "no-signal":
            mk_arm(d, "OS_LGC", 36, (1000, 500, 2800, 1100), [("MAIN", 800), ("python3", 400)])
            mk_arm(d, "OS_SPEC", 37, (1000, 500, 2900, 1150), [("MAIN", 850), ("python3", 400)])
        elif name == "reversed":
            mk_arm(d, "OS_LGC", 36, (1000, 500, 3600, 1400), [("MAIN", 1700), ("python3", 400)])
            mk_arm(d, "OS_SPEC", 36, (1000, 500, 2800, 1100), [("MAIN", 800), ("python3", 400)])
        elif name == "identify-fail":
            mk_arm(d, "OS_LGC", 36, (1000, 500, 2800, 1100), [("MAIN", 800), ("python3", 400)])
            mk_arm(d, "OS_SPEC", 43, (1000, 500, 3600, 1400), [("MAIN", 1700), ("python3", 450)])
            d2 = build(name, src="deadbeef")
            shutil.move(os.path.join(d, "out"), os.path.join(d2, "out"))
            shutil.rmtree(d)
            d = d2
        elif name == "data-fail":
            mk_arm(d, "OS_LGC", 36, (1000, 500, 2800, 1100), [("MAIN", 800), ("python3", 400)])
            mk_arm(d, "OS_SPEC", 43, (1000, 500, 3600, 1400), [("MAIN", 1700), ("python3", 450)])
            os.remove(os.path.join(d, "out", "OS_SPEC.tidcsv"))
        elif name == "coverage-out":
            # process Dcpu = 12s but buckets only carry 2.4s -> coverage 0.2
            mk_arm(d, "OS_LGC", 36, (1000, 500, 2800, 1100), [("MAIN", 800), ("python3", 400)])
            mk_arm(d, "OS_SPEC", 43, (1000, 500, 3600, 1400), [("MAIN", 900), ("python3", 440)])
        rc, out = run(d)
        ok = (rc == expect) and (grep is None or grep in out)
        results.append((name, expect, rc, ok))
        print(f"{'PASS' if ok else 'FAIL'} {name}: expect rc={expect} got rc={rc}" + (f" grep={grep!r} {'found' if grep in out else 'MISSING'}" if grep else ""))
        if not ok:
            print(out[:800])
        shutil.rmtree(d, ignore_errors=True)
    n_ok = sum(1 for r in results if r[3])
    print(f"\n{n_ok}/{len(results)} PASS")
    return 0 if n_ok == len(results) else 1

if __name__ == "__main__":
    sys.exit(main())
