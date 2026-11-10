#!/usr/bin/env python3
"""analyze764.py — exp764: py-spy stack attribution of the SPEC untraced-time cost.

Preregistered: PREREG-764.md (sha frozen in FREEZE-764.txt BEFORE profiles).
Parses two py-spy raw collapsed-stack files (100 Hz): PROF_LGC.pyspy, PROF_SPEC.pyspy.
Self-time = leaf-frame sampling attribution; seconds = counts / 100.
Families (leaf frame "func (file:line)"; checked in order):
  F2 verify:       file has 'spec_decode' AND (func has 'verify' or 'acceptance')
  F1 spec-policy:  file has 'spec_decode' (draft/sampling/prefetch-route loop)
  F3 reshape/sched: file has 'model_offload' or 'big_modeling' or ('runtime' and 'offload')
  F4 kernel glue:  leaf starts 'aten::' or contains 'torch'/'cuda'/'built-in'/'{method}'
  F5 other:        rest
Decision: delta_i = seconds_SPEC(F_i) - seconds_LGC(F_i); positive-total P = sum of
positive deltas. A5 if max delta >= 0.5*P; else A2 if top-2 >= 0.7*P; else A0.
Exit 0 ATTRIBUTED-A5|A2|A0 (label per rule; A0 still exits 0 with ATTRIBUTED-A0-DIFFUSE),
3 INCONCLUSIVE (combined samples < 30000), 4 DATA-FAIL (missing/malformed files),
9 IDENTIFY-FAIL (SRC_HEAD != b7f6ca4... or env fingerprint mismatch).
Immutable after freeze.
"""
import os, re, sys

HZ = 100.0
MIN_SAMPLES = 30000
SRC_EXPECT = "b7f6ca4d2caa5229698d78deb03b454fc20947dd"

def fail(code, msg):
    print(msg); sys.exit(code)

def family(leaf):
    # leaf like: "func (pkg/file.py:12)" or "aten::mm" or "{method 'mm' of 'torch...'}"
    m = re.search(r"\(([^()]*\.py)[^()]*\)\s*$", leaf)
    fn = m.group(1) if m else ""
    base = leaf.split(" (")[0]
    if "spec_decode" in fn and re.search(r"verify|acceptance", base):
        return "F2_verify"
    if "spec_decode" in fn:
        return "F1_spec_policy"
    if "model_offload" in fn or "big_modeling" in fn or ("runtime" in fn and "offload" in fn):
        return "F3_reshape_sched"
    if leaf.startswith("aten::") or "torch" in leaf or "cuda" in leaf or "built-in" in leaf or leaf.startswith("{method"):
        return "F4_kernel_glue"
    return "F5_other"

def load(path):
    if not os.path.exists(path):
        fail(4, f"DATA-FAIL: missing {path}")
    fams, leaves, total = {}, {}, 0
    for ln, line in enumerate(open(path, errors="replace"), 1):
        line = line.rstrip("\n")
        if not line:
            continue
        m = re.match(r"^(.*) (\d+)$", line)
        if not m:
            fail(4, f"DATA-FAIL: malformed raw line {ln} in {path}: {line[:60]!r}")
        stack, cnt = m.group(1), int(m.group(2))
        leaf = stack.split(";")[-1].strip()
        f = family(leaf)
        fams[f] = fams.get(f, 0) + cnt
        leaves[leaf] = leaves.get(leaf, 0) + cnt
        total += cnt
    return fams, leaves, total

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "out"
    sh = os.path.join(d, "SRC_HEAD.txt")
    if not os.path.exists(sh):
        fail(9, "IDENTITY-FAIL: missing SRC_HEAD.txt")
    head = open(sh).read().strip()
    if not head.startswith(SRC_EXPECT[:12]):
        fail(9, f"IDENTIFY-FAIL: SRC_HEAD {head[:12]} != {SRC_EXPECT[:12]}")
    ev = os.path.join(d, "ENV.txt")
    if os.path.exists(ev):
        t = open(ev, errors="replace").read()
        if "moei-RC753" not in t or "/home/mfeth/exp759/src753/moe_infinity" not in t:
            fail(9, "IDENTIFY-FAIL: ENV fingerprint mismatch")
    fl, ll, tl = load(os.path.join(d, "PROF_LGC.pyspy"))
    fs, ls, ts = load(os.path.join(d, "PROF_SPEC.pyspy"))
    if tl + ts < MIN_SAMPLES:
        fail(3, f"VERDICT: INCONCLUSIVE (samples {tl+ts} < {MIN_SAMPLES})")
    FAMS = ["F1_spec_policy", "F2_verify", "F3_reshape_sched", "F4_kernel_glue", "F5_other"]
    print(f"samples: LGC {tl} ({tl/HZ:.1f}s) SPEC {ts} ({ts/HZ:.1f}s)")
    deltas = {}
    for f in FAMS:
        l, s = fl.get(f, 0) / HZ, fs.get(f, 0) / HZ
        deltas[f] = s - l
        print(f"{f:16s} LGC {l:7.2f}s  SPEC {s:7.2f}s  Δ {s-l:+8.2f}s")
    pos = {f: d_ for f, d_ in deltas.items() if d_ > 0}
    P = sum(pos.values())
    print(f"positive delta total P = {P:.2f}s")
    if P <= 0:
        print("VERDICT: ATTRIBUTED-A0-DIFFUSE (no positive delta families)")
        sys.exit(0)
    ranked = sorted(pos.items(), key=lambda kv: -kv[1])
    top1 = ranked[0][1] / P
    top2 = sum(v for _, v in ranked[:2]) / P
    print(f"top-family share {ranked[0][0]} = {top1:.1%}; top-2 = {top2:.1%}")
    print("SPEC top-10 leaves by self-time:")
    for leaf, c in sorted(ls.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {c/HZ:7.2f}s  {leaf[:110]}")
    if top1 >= 0.5:
        print(f"VERDICT: ATTRIBUTED-A5 {ranked[0][0]} ({top1:.1%} of positive delta)")
    elif top2 >= 0.7:
        print(f"VERDICT: ATTRIBUTED-A2 {ranked[0][0]}+{ranked[1][0]} ({top2:.1%} combined)")
    else:
        print("VERDICT: ATTRIBUTED-A0-DIFFUSE")
    sys.exit(0)

if __name__ == "__main__":
    main()
