#!/usr/bin/env python3
"""exp765 fixture battery: synthetic raw stacks exercising every verdict branch
and every gate. Ground truth computed by hand. Run BEFORE freeze."""
import os, subprocess, sys, shutil

BASE = "/Users/mfethe/.hermes/cache/scratch/exp767-fixtures"
ANA = "/Users/mfethe/warp-work/exp765-prefetch-cost-repair/analyze767.py"
SRC_OK = "b7f6ca4d2caa5229698d78deb03b454fc20947dd\n"
WRAP = "speculative_prefetch (moe_infinity/distributed/expert_executor.py:209)"
PREF = "speculative_prefetch (moe_infinity/memory/expert_prefetcher.py:450)"
ROOT = "<module> (engine_arm765.py:178);main (engine_arm765.py:139)"

def mk(name, lgc_lines, spec_lines, src=SRC_OK, drop_file=None):
    d = os.path.join(BASE, name)
    out = os.path.join(d, "out"); os.makedirs(out, exist_ok=True)
    if drop_file != "NAT_LGC.pyspy": open(os.path.join(out, "NAT_LGC.pyspy"), "w").write(lgc_lines)
    if drop_file != "NAT_SPEC.pyspy": open(os.path.join(out, "NAT_SPEC.pyspy"), "w").write(spec_lines)
    if src is not None: open(os.path.join(out, "SRC_HEAD.txt"), "w").write(src)
    return d

def inside_leaf(leaf, n, wrap=WRAP): return f"{ROOT};{wrap};{PREF};{leaf} {n}\n"
FILLER = f"{ROOT};idle (idlelib.py:1) 16000\n"

# D1 native-rich: SPEC adds 8.0 s inside, 7.0 of it N_TORCH+N_HEX
lgc = inside_leaf("at::_ops::topk::call (libtorch_cpu.so)", 100) + inside_leaf("speculative_prefetch (moe_infinity/memory/expert_prefetcher.py:447)", 100)
spec = inside_leaf("at::_ops::topk::call (libtorch_cpu.so)", 700) + inside_leaf("0x7f8670e2a1ca (libc.so.6)", 100) + inside_leaf("speculative_prefetch (moe_infinity/memory/expert_prefetcher.py:447)", 100) + f"{ROOT};generate (other.py:9) 4000\n"
mk("d1", lgc + FILLER, spec + FILLER)
# D2 python-rich: SPEC adds 8.0 s inside, 7.2 python leaf
lgc2 = inside_leaf(PREF, 100)
spec2 = inside_leaf(PREF, 820) + inside_leaf("memcpy (libc.so.6)", 80) + f"{ROOT};x (z.py:1) 3000\n"
mk("d2", lgc2 + FILLER, spec2 + FILLER)
# D3 mixed: 4.5 native / 4.5 python
spec3 = inside_leaf("cudaMemcpyAsync (libc.so.6)", 450) + inside_leaf(PREF, 450) + f"{ROOT};x (z.py:1) 3000\n"
mk("d3", lgc2 + FILLER, spec3 + FILLER)
# sample gate: tiny files
mk("gate", inside_leaf(PREF, 10), inside_leaf(PREF, 20))
# src fail
mk("src", lgc + FILLER, spec + FILLER, src="deadbeef\n")
# data fail: missing SPEC file
mk("data", lgc, spec, drop_file="NAT_SPEC.pyspy")
# D5 null-time: P = 0.5 s
spec5 = inside_leaf(PREF, 150) + f"{ROOT};x (z.py:1) 3000\n"
mk("d5", lgc2 + FILLER, spec5 + FILLER)

EXPECT = {"d1": "1", "d2": "2", "d3": "4", "gate": "3", "src": "9", "data": "4", "d5": "5"}
fails = []
for name, want in EXPECT.items():
    r = subprocess.run([sys.executable, ANA, os.path.join(BASE, name)], capture_output=True, text=True)
    got = [l for l in r.stdout.splitlines() if l.startswith("rc=")]
    got = got[-1][3:] if got else f"NO-RC(exit={r.returncode})"
    ok = got == want and (name != "data" or "DATA-FAIL" in r.stdout)
    status = "PASS" if ok else "FAIL"
    if not ok: fails.append(name)
    v = [l for l in r.stdout.splitlines() if "VERDICT" in l or "rc=" in l or "FAIL" in l or "share" in l or "INCONCLUSIVE" in l or "NULL" in l]
    print(f"{status} {name}: want rc={want} got rc={got} :: {' | '.join(v)[:150]}")
print("BATTERY:", "ALL PASS" if not fails else f"FAILED {fails}")
sys.exit(1 if fails else 0)
