#!/usr/bin/env python3
"""fixtures778.py — battery for analyze778.py (synthetic collapsed stacks)."""
import hashlib, os, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(BASE, "analyze778.py")

def mk(dirname, lines):
    d = tempfile.mkdtemp(prefix=dirname + "-")
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    for cid in ["PY_R075", "PY_R100"]:
        p = os.path.join(d, "out", cid + ".pyspy")
        open(p, "w").write("\n".join(lines[cid]) + "\n")
        sha = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
        # patch the expected sha directly into the analyzer copy
    return d

def patchsha(d, shas):
    an = os.path.join(d, "an778.py")
    src = open(AN).read()
    import re
    src = re.sub(r'SHA = \{[^}]*\}', "SHA = " + repr(shas), src)
    open(an, "w").write(src)
    return an

def run(an, d):
    r = subprocess.run([sys.executable, an, d, d], capture_output=True, text=True)
    rc = None
    for ln in r.stdout.splitlines():
        if ln.startswith("rc="):
            rc = int(ln[3:])
    return rc, r.stdout + r.stderr

S_ATT = "_sample (generation/utils.py:1);OlmoeAttention.forward (modeling_olmoe.py:1);sdpa (x:1)"
S_MLP = "_sample (generation/utils.py:1);OlmoeSparseMoeBlock.forward (modeling_olmoe.py:1)"
S_GEN = "_sample (generation/utils.py:1);sampler776 (s:1);logits_processor (x:1)"
S_NRM = "_sample (g:1);RMSNorm.forward (n:1);embed_tokens (e:1)"
S_OTH = "worker (w:1);unknown_thing (u:1)"
S_LOAD = "archer_from_pretrained (model_offload.py:1);safetensors (s:1)"
S_EXP = "_sample (g:1);prefetch (moe_infinity/memory/expert_prefetcher.py:1)"

def _wrap(lines):
    return [s + f" {(i % 3) + 1}" for i, s in enumerate(lines)]

def mix(d):
    return {
        # attn 40% of non-load -> ATTRIBUTED
        "attr": {"PY_R075": [S_ATT]*40 + [S_MLP]*20 + [S_GEN]*15 + [S_NRM]*10 + [S_OTH]*15 + [S_LOAD]*10,
                  "PY_R100": [S_ATT]*38 + [S_MLP]*22 + [S_GEN]*16 + [S_NRM]*9 + [S_OTH]*15 + [S_LOAD]*12},
        # top = other 22% -> PARTIAL
        "partial": {"PY_R075": [S_OTH]*22 + [S_ATT]*20 + [S_MLP]*20 + [S_GEN]*19 + [S_NRM]*19 + [S_LOAD]*5,
                     "PY_R100": [S_OTH]*21 + [S_ATT]*21 + [S_MLP]*20 + [S_GEN]*19 + [S_NRM]*19 + [S_LOAD]*5},
        # six buckets equal (1/6 each? no: 6 non-load buckets + OTHER... equal -> top <15% -> DIFFUSE
        "diffuse": {"PY_R075": [S_ATT]*70 + [S_MLP]*70 + [S_GEN]*70 + [S_NRM]*70 + [S_OTH]*70 + [S_EXP]*70 + [S_LOAD]*30,
                     "PY_R100": [S_MLP]*70 + [S_ATT]*70 + [S_GEN]*70 + [S_NRM]*70 + [S_OTH]*70 + [S_EXP]*70 + [S_LOAD]*30},
        # load only -> DATA
        "loadonly": {"PY_R075": [S_LOAD]*50, "PY_R100": [S_LOAD]*50},
    }

CASES = [("attr", 1, "ATTRIBUTED"), ("partial", 2, "PARTIAL"), ("diffuse", 7, "DIFFUSE"), ("loadonly", 4, "DATA-FAIL")]

def main():
    def mix2(name):
        return {cid: _wrap(v) for cid, v in cases_raw[name].items()}
    ok = tot = 0
    cases_raw = mix(None)
    for name, expect, grep in CASES:
        d = mk(name, mix2(name))
        shas = {}
        for cid in ["PY_R075", "PY_R100"]:
            shas[cid] = hashlib.sha256(open(os.path.join(d, "out", cid + ".pyspy"), "rb").read()).hexdigest()[:16]
        an = patchsha(d, shas)
        rc, out = run(an, d)
        good = rc == expect and grep in out
        ok += good; tot += 1
        print(f"{'PASS' if good else 'FAIL'} {name}: expect rc={expect} got rc={rc} grep {'ok' if grep in out else 'MISSING'}")
        if not good: print(out[-400:])
        # sha-mismatch identify case (run once, on attr fixture)
        if name == "attr":
            an2 = patchsha(d, {"PY_R075": "badbadbadbadbad0", "PY_R100": shas["PY_R100"]})
            rc2, out2 = run(an2, d)
            good2 = rc2 == 9 and "IDENTIFY-FAIL" in out2
            ok += good2; tot += 1
            print(f"{'PASS' if good2 else 'FAIL'} sha-mismatch: expect rc=9 got rc={rc2}")
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{ok}/{tot} PASS")
    return 0 if ok == tot else 1

if __name__ == "__main__":
    sys.exit(main())
