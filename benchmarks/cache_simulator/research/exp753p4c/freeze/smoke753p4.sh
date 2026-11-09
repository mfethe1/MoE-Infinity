#!/bin/bash
# exp753p4c pre-freeze smoke v2 (PREREG-P4C.md §6; NOT measurement cells; no timing claims).
# v2 changes (review F5/F10): row lookup by prompt identity (sha of applied prompt text), explicit
# force_steps presence check, negative banner check on the no-force control, S3 = C-style forced
# run (trace+timing ON) so BOTH engine construction paths used by the measurement are exercised,
# prompts fixture hashes recorded (review F4).
# S1 WITH --force-steps on [p0, p4], A-style: mechanism (p4 -> 64 tokens, EOS kept in-stream at
#    index 20) + flag inertness (p0 strict 64/64 == ref[0]; ref[0] IS the sealed unforced stream)
#    + provenance readback (eos_before=50279, eos_after=-1).
# S2 WITHOUT --force-steps on [p4], A-style (deliberate single-edit mutation; metric must BITE):
#    reproduces the sealed exp753 behavior (n_new==21, out_ids == ref[4] 21/21); banner of the
#    forced path must be ABSENT.
# S3 WITH --force-steps on [p4], C-style (trace+timing ON): same p4 gate + provenance.
# PASS requires all; else BLOCKED-MECHANISM, no measurement cell runs.
cd ~/exp753p4; source ~/venvs/moei-engine/bin/activate; mkdir -p out
python3 - <<'PY'
import hashlib, json
p = json.load(open('prompts.json'))
json.dump([p[0], p[4]], open('prompts_p4smoke.json', 'w'))
json.dump([p[4]], open('prompts_p4only.json', 'w'))
hs = {f"p{i}": hashlib.sha256(p[i].encode()).hexdigest()[:16] for i in range(6)}
json.dump(hs, open('out/SMOKE-PROMPT-HASHES.json', 'w'), indent=1)
print("prompt-hashes", hs)
PY
M=~/models/OLMoE-1B-7B-0125-Instruct
echo "== $(date -u +%FT%TZ) p4c smoke v2: quiet gate"
QW=$(bash allquiet746.sh 1 5400 </dev/null); echo "qw=$QW"
export CUDA_VISIBLE_DEVICES=1
rm -f out/SMOKE_P4C_FORCE.json out/SMOKE_P4C_NOFORCE.json out/SMOKE_P4C_FORCEC.json out/SMOKE-P4C.txt
env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
  timeout 1500 python3 engine_arm753_p4.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
  --threads 4 --gpu-route on --prompts prompts_p4smoke.json --max-new 64 --warmup 1 --arm-name A --timing off \
  --force-steps --out out/SMOKE_P4C_FORCE.json > out/SMOKE_P4C_FORCE.log 2>&1 </dev/null
RC1=$?
QW=$(bash allquiet746.sh 1 5400 </dev/null); echo "qw2=$QW"
env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
  timeout 1500 python3 engine_arm753_p4.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
  --threads 4 --gpu-route on --prompts prompts_p4only.json --max-new 64 --warmup 1 --arm-name A --timing off \
  --out out/SMOKE_P4C_NOFORCE.json > out/SMOKE_P4C_NOFORCE.log 2>&1 </dev/null
RC2=$?
QW=$(bash allquiet746.sh 1 5400 </dev/null); echo "qw3=$QW"
env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
  MOEI_EXP753_TRACE=1 MOEI_EXP753_TRACE_FILE=/home/mfeth/exp753p4/out/SMOKE_P4C_FORCEC.trace.jsonl \
  timeout 1500 python3 engine_arm753_p4.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
  --threads 4 --gpu-route on --prompts prompts_p4only.json --max-new 64 --warmup 1 --arm-name C --timing on \
  --force-steps --out out/SMOKE_P4C_FORCEC.json > out/SMOKE_P4C_FORCEC.log 2>&1 </dev/null
RC3=$?
python3 - "$RC1" "$RC2" "$RC3" <<'PY'
import hashlib, json, sys
rc1, rc2, rc3 = map(int, sys.argv[1:4])
ok = [f"rc_force={rc1}", f"rc_noforce={rc2}", f"rc_forceC={rc3}"]
allok = (rc1 == 0 and rc2 == 0 and rc3 == 0)
ref = json.load(open('refs/engine_ref.json'))["out_ids"]
prompts = json.load(open('prompts.json'))
ph = {i: hashlib.sha256(prompts[i].encode()).hexdigest()[:16] for i in range(6)}

def row_by_prompt(d, want_idx):
    for r in d['rows']:
        if r.get('i') == want_idx:
            return r
    return None

def check_forced(cell, p4idx, logname, want_arm):
    global allok
    try:
        d = json.load(open(f'out/{cell}.json'))
    except Exception as e:
        ok.append(f"{cell}: LOAD_ERR={e!r}"); allok = False; return
    fs = d.get('force_steps')
    prov = (isinstance(fs, dict) and fs.get('eos_before') == 50279 and fs.get('eos_after') == -1
            and fs.get('row_lens') == [64] * len(d['rows']))
    ok.append(f"{cell}: prov={prov}({fs})"); allok &= prov
    r4 = row_by_prompt(d, p4idx)
    if r4 is None:
        ok.append(f"{cell}: p4 row missing"); allok = False; return
    got = r4['out_ids']
    m4 = (r4['n_new'] == 64 and len(got) == 64 and got[:21] == ref[4] and got[20] == 50279)
    ok.append(f"{cell}: p4gate={m4}(n_new={r4['n_new']},len={len(got)},prefix21={got[:21]==ref[4]},eos20={got[20]==50279 if len(got)>20 else None})")
    allok &= m4
    txt = open(f'out/{logname}').read()
    b = (f'exp753 mode={want_arm}' in txt and 'exp753p4c force-steps' in txt)
    ok.append(f"{cell}: banners={b}"); allok &= b

# S1: forced, A-style, [p0, p4]
check_forced('SMOKE_P4C_FORCE', 1, 'SMOKE_P4C_FORCE.log', 'A')
try:
    d = json.load(open('out/SMOKE_P4C_FORCE.json'))
    r0 = row_by_prompt(d, 0)
    m0 = (r0 is not None and r0['out_ids'] == ref[0] and r0['n_new'] == 64 and len(r0['out_ids']) == 64)
    ok.append(f"S1 p0_strict64={m0}"); allok &= m0
except Exception as e:
    ok.append(f"S1 p0_ERR={e!r}"); allok = False
# S2: no-force control (mutation contrast)
try:
    d = json.load(open('out/SMOKE_P4C_NOFORCE.json'))
    fs = d.get('force_steps')
    absent = ('force_steps' in d and d['force_steps'] is None)
    ok.append(f"S2 prov_key_absent={absent}"); allok &= absent
    r4 = row_by_prompt(d, 0)
    got = r4['out_ids']
    m = (r4['n_new'] == 21 and got == ref[4])
    ok.append(f"S2 p4_reproduces21={m}(n_new={r4['n_new']},len={len(got)})"); allok &= m
    txt = open('out/SMOKE_P4C_NOFORCE.log').read()
    nb = ('exp753p4c force-steps' not in txt and 'exp753 mode=A trace=0 timing=off' in txt)
    ok.append(f"S2 negative_banner={nb}"); allok &= nb
except Exception as e:
    ok.append(f"S2 ERR={e!r}"); allok = False
# S3: forced, C-style (trace+timing), [p4]
check_forced('SMOKE_P4C_FORCEC', 0, 'SMOKE_P4C_FORCEC.log', 'C')
try:
    d = json.load(open('out/SMOKE_P4C_FORCEC.json'))
    tsf = bool(d.get('timing_setter_found'))
    ok.append(f"S3 timing_setter={tsf}"); allok &= tsf
except Exception as e:
    ok.append(f"S3 ts_ERR={e!r}"); allok = False
verdict = "SMOKE-P4C-PASS" if allok else "SMOKE-P4C-FAIL"
open('out/SMOKE-P4C.txt', 'w').write(verdict + " " + " ".join(ok) + "\n")
print(verdict, *ok, sep="\n")
PY
echo "== $(date -u +%FT%TZ) p4c smoke v2 done"
