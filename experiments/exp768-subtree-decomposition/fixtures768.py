#!/usr/bin/env python3
"""fixtures768: synthetic sealed-stack sets exercising every branch of analyze768."""
import os, shutil, subprocess, sys, tempfile

BASE = tempfile.mkdtemp(prefix="exp768-fixtures-")
SPF = "speculative_prefetch (moe_infinity/distributed/expert_executor.py:209);x (a.py:1)"
EAG = "DistributedExpertExecutor._dispatch_eager_local (moe_infinity/distributed/expert_executor.py:856);y (b.py:2)"
WAI = "DistributedExpertExecutor.wait_dispatch_local (moe_infinity/distributed/expert_executor.py:900);z (c.py:3)"
FILLER_PY = "main (engine_arm.py:10);gen (engine_arm.py:20)"
FILLER_NAT = "main (engine_arm.py:10);0x7f0000000100"

def write_arm(d, arm, n_spec, n_eager, n_wait, filler):
    os.makedirs(f"{d}/out", exist_ok=True)
    with open(f"{d}/out/NAT_{arm}.pyspy", "w") as f:
        f.write(f"{SPF} {n_spec}\n{EAG} {n_eager}\n{WAI} {n_wait}\n")
        f.write(f"{FILLER_PY} {filler//2}\n{FILLER_NAT} {filler - filler//2}\n")

def mk(name, lgc, spec, src="b7f6ca4d2caa5229698d78deb03b454fc20947dd", drop_spec=False):
    d = f"{BASE}/{name}"; os.makedirs(f"{d}/out", exist_ok=True)
    write_arm(d, "LGC", *lgc[:3], lgc[3]); write_arm(d, "SPEC", *spec[:3], spec[3])
    if src: open(f"{d}/out/SRC_HEAD.txt", "w").write(src)
    if drop_spec: os.remove(f"{d}/out/NAT_SPEC.pyspy")
    return d

F = 16000
cases = [
    ("D3-NETNULL",   mk("d3", (600, 700, 800, F), (600, 690, 810, F)), 5),
    ("D1-EAGER",     mk("d1", (600, 600, 900, F), (600, 900, 900, F)), 1),
    ("D2-MIGRATION", mk("d2", (600, 700, 900, F), (1000, 700, 650, F)), 2),
    ("D4-MIXED",     mk("d4", (600, 600, 900, F), (900, 650, 850, F)), 6),
    ("INCONCL",      mk("ic", (400, 700, 900, F), (600, 700, 900, F)), 3),
    ("IDENTIFY",     mk("id", (600, 700, 800, F), (600, 700, 800, F), src="deadbeef00"), 9),
    ("DATA-FAIL",    mk("df", (600, 700, 800, F), (600, 700, 800, F), drop_spec=True), 4),
]
ok = 0
for name, d, want in cases:
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze768.py"), d, d],
                       capture_output=True, text=True)
    got = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="): got = int(ln[3:])
    ok += (got == want)
    print(f"{name:12s} want rc={want} got rc={got} {'PASS' if got == want else 'FAIL'}")
print(f"{ok}/{len(cases)} PASS")
shutil.rmtree(BASE)
sys.exit(0 if ok == len(cases) else 1)
