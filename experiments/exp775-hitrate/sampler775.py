#!/usr/bin/env python3
"""sampler770.py PIDFILE OUT.csv TIDCSV [HZ] — per-thread /proc sampler.

Extends sampler769.py (same process-level columns, verbatim field mapping) with
a second output: per-tick aggregation of /proc/<pid>/task/*/stat grouped by
thread bucket. Bucket = "MAIN" for tid==pid (thread-group leader), else the
thread's comm (parenthesized field 2 of stat). One row per (tick, bucket):
t,bucket,nthreads,utime_sum_t,stime_sum_t (sums over threads in that bucket,
in clock ticks). Separate process; procfs reads only.
"""
import os, sys, time

pidfile, out, tout = sys.argv[1], sys.argv[2], sys.argv[3]
hz = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0
CLK = os.sysconf("SC_CLK_TCK")

deadline = time.time() + 900
while not os.path.exists(pidfile) and time.time() < deadline:
    time.sleep(0.5)
try:
    pid = int(open(pidfile).read().strip())
except Exception:
    sys.exit(4)

def rd(p):
    try:
        return open(p).read()
    except Exception:
        return ""

f = open(out, "w")
f.write(f"# clk_tck={CLK}\n")
f.write("t,utime_t,stime_t,threads,minflt,majflt,rss_kb,vol,nonvol,read_kb,write_kb\n")
g = open(tout, "w")
g.write(f"# clk_tck={CLK} pid={pid}\n")
g.write("t,bucket,nthreads,utime_sum_t,stime_sum_t\n")

def sample_tasks():
    """Return dict bucket -> [n, utime_sum, stime_sum] for live threads."""
    agg = {}
    tdir = f"/proc/{pid}/task"
    try:
        tids = os.listdir(tdir)
    except Exception:
        return None
    for tid in tids:
        st = rd(f"{tdir}/{tid}/stat")
        if not st:
            continue
        try:
            op = st.index("(")
            cp = st.rindex(")")
            tidv = int(st[:op])
            comm = st[op + 1:cp].strip()
            rest = st[cp + 2:].split()
            utime, stime = int(rest[11]), int(rest[12])  # fields 14,15
        except Exception:
            continue
        bucket = "MAIN" if tidv == pid else comm
        a = agg.get(bucket)
        if a is None:
            agg[bucket] = [1, utime, stime]
        else:
            a[0] += 1
            a[1] += utime
            a[2] += stime
    return agg

n = 0
while True:
    t = time.time()
    st = rd(f"/proc/{pid}/stat")
    if not st:
        break
    try:
        rest = st[st.rindex(")") + 2:].split()  # fields from state (field3) on
        utime, stime = rest[11], rest[12]       # fields 14,15
        threads = rest[17]                      # field 20
        minflt, majflt = rest[6], rest[8]       # fields 9,11
    except Exception:
        break
    rss = vol = nonvol = "-1"
    for ln in rd(f"/proc/{pid}/status").splitlines():
        if ln.startswith("VmRSS:"): rss = ln.split()[1]
        elif ln.startswith("voluntary_ctxt_switches:"): vol = ln.split()[1]
        elif ln.startswith("nonvol_ctxt_switches:") or ln.startswith("nonvoluntary_ctxt_switches:"): nonvol = ln.split()[1]
    read_kb = write_kb = "-1"
    for ln in rd(f"/proc/{pid}/io").splitlines():
        if ln.startswith("read_bytes:"): read_kb = ln.split()[1]
        elif ln.startswith("write_bytes:"): write_kb = ln.split()[1]
    f.write(f"{t:.3f},{utime},{stime},{threads},{minflt},{majflt},{rss},{vol},{nonvol},{read_kb},{write_kb}\n")
    agg = sample_tasks()
    if agg is not None:
        for bucket in sorted(agg):
            a = agg[bucket]
            g.write(f"{t:.3f},{bucket},{a[0]},{a[1]},{a[2]}\n")
    n += 1
    if n % 400 == 0:
        f.flush()
        g.flush()
    time.sleep(max(0.0, 1.0 / hz - (time.time() - t)))
f.write(f"# exited samples={n}\n")
g.write(f"# exited samples={n}\n")
f.close()
g.close()
