#!/usr/bin/env python3
"""fixtures769: synthetic json+csv pairs exercising every analyze769 branch."""
import json, os, shutil, subprocess, sys, tempfile

BASE = tempfile.mkdtemp(prefix="exp769-fixtures-")
CLK = 100  # clk_tck written in csv meta line

def mk_arm(d, arm, t_each, cpu_secs, minf=0, majf=0, nonvol=0, n_rows=6, n_samples=300, t0=1000.0, threads=8, rss=5_000_000):
    os.makedirs(f"{d}/out", exist_ok=True)
    rows = []
    for i in range(n_rows):
        w0 = t0 + i * 50
        rows.append({"i": i, "t_1tok_s": t_each[0], "t_full_s": t_each[1], "win_full": [w0, w0 + 40],
                     "decode_tok_s": 5.0, "n_in": 10, "n_new": 64})
    json.dump({"rows": rows}, open(f"{d}/out/{arm}.json", "w"))
    win0, win1 = rows[0]["win_full"][0], rows[-1]["win_full"][1]
    with open(f"{d}/out/{arm}.oscsv", "w") as f:
        f.write(f"# clk_tck={CLK}\n")
        f.write("t,utime_t,stime_t,threads,minflt,majflt,rss_kb,vol,nonvol,read_kb,write_kb\n")
        for k in range(n_samples):
            t = win0 - 5 + k * ((win1 - win0 + 10) / n_samples)
            frac = (t - (win0 - 5)) / (win1 - win0 + 10)
            u = int(cpu_secs * CLK * frac / 2); s_ = int(cpu_secs * CLK * frac / 2)
            f.write(f"{t:.3f},{u},{s_},{threads},{int(minf*frac)},{int(majf*frac)},{rss},{int(1000*frac)},{int(nonvol*frac)},{int(500*frac)},{int(100*frac)}\n")
    return sum(r["t_1tok_s"] + r["t_full_s"] for r in rows)

def mk(name, lgc_kw, spec_kw, src="b7f6ca4d2caa5229698d78deb03b454fc20947dd", drop=None, short_rows=False, short_samples=False):
    d = f"{BASE}/{name}"; os.makedirs(f"{d}/out", exist_ok=True)
    Wl = mk_arm(d, "OS_LGC", **({**lgc_kw, "n_rows": 3} if short_rows else lgc_kw))
    Ws = mk_arm(d, "OS_SPEC", **({**spec_kw, "n_samples": 40} if short_samples else spec_kw))
    if src: open(f"{d}/out/SRC_HEAD.txt", "w").write(src)
    if drop: os.remove(f"{d}/out/OS_{drop}.oscsv")
    return d, Wl, Ws

BASE_KW = dict(t_each=(1.0, 40.0), cpu_secs=120.0)  # W = 6*(1+40) = 246s/arm
T = lambda: dict(BASE_KW)
cases = []
# D5 NO-REPLICATION: identical arms
cases.append(("D5-NOREPL", *mk("d5", T(), dict(t_each=(1.0, 40.1), cpu_secs=120.0)), 5))
# D1 CPU-DOMINATED: DW = +6s, Dcpu = +5.5s >= 0.8*6=4.8
cases.append(("D1-CPU", *mk("d1", T(), dict(t_each=(1.0, 41.0), cpu_secs=125.5)), 1))
# D2 FAULT-DOMINATED: DW=+6, Dcpu=+2 (<4.8), Dmaj=+150k
cases.append(("D2-FAULT", *mk("d2", T(), dict(t_each=(1.0, 41.0), cpu_secs=122.0, majf=150000)), 2))
# D3 SCHED: DW=+6, Dcpu=+2, no faults, Dnonvol=+600k
cases.append(("D3-SCHED", *mk("d3", T(), dict(t_each=(1.0, 41.0), cpu_secs=122.0, nonvol=600000)), 6))
# D4 UNATTRIBUTED: DW=+6, Dcpu=+2, faults/nonvol tiny
cases.append(("D4-UNATTR", *mk("d4", T(), dict(t_each=(1.0, 41.0), cpu_secs=122.0, minf=10000, nonvol=1000)), 7))
# D6 REVERSED: DW = -6s
cases.append(("D6-REVERSED", *mk("d6", dict(t_each=(1.0, 41.0), cpu_secs=120.0), T()), 8))
# IDENTIFY-FAIL
cases.append(("IDENTIFY", *mk("id", T(), T(), src="deadbeef00"), 9))
# DATA-FAIL: dropped csv
cases.append(("DATA-DROP", *mk("dd", T(), T(), drop="SPEC"), 4))
# DATA-FAIL: rows<6 in LGC
cases.append(("DATA-ROWS", *mk("dr", T(), T(), short_rows=True), 4))
# DATA-FAIL: in-window samples < 100 in SPEC
cases.append(("DATA-SAMP", *mk("ds", T(), T(), short_samples=True), 4))

ok = 0
for name, d, Wl, Ws, want in cases:
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze769.py"), d, d],
                       capture_output=True, text=True)
    got = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="): got = int(ln[3:])
    ok += (got == want)
    print(f"{name:12s} want rc={want} got rc={got} {'PASS' if got == want else 'FAIL'}")
print(f"{ok}/{len(cases)} PASS")
shutil.rmtree(BASE)
sys.exit(0 if ok == len(cases) else 1)
