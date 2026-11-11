#!/usr/bin/env python3
"""sampler769.py PIDFILE OUT.csv [HZ] — /proc sampler in a SEPARATE process.

Waits for PIDFILE (up to 900 s), then samples /proc/<pid>/stat, status, io at HZ
(default 20) until the process exits. Separate process => no GIL contention with
the engine; reads are procfs only. Writes a meta header with clk_tck.
"""
import os, sys, time

pidfile, out = sys.argv[1], sys.argv[2]
hz = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
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
    n += 1
    if n % 400 == 0: f.flush()
    time.sleep(max(0.0, 1.0 / hz - (time.time() - t)))
f.write(f"# exited samples={n}\n")
f.close()
