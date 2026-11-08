#!/bin/bash
# exp753 pre-freeze smoke (NOT a measurement cell; no timing claims): 2 prompts, trace+timing ON (C-style) and a
# trace-OFF (A-style) run on the private build. PASS requires: both RC=0; tokens match engine_ref on prompts 0-1
# (strict prompts, 64/64); C-style trace has records>0, dropped==0, KERN(site15)>0, SETINPUTS_ENTER==EXIT-with-id;
# A-style produces NO trace file. Banner present. Runs quiet-gated on GPU1.
cd ~/exp753; source ~/venvs/moei-engine/bin/activate; mkdir -p out
python3 - <<'PY'
import json
p=json.load(open('prompts.json')); json.dump(p[:2], open('prompts_smoke.json','w'))
PY
M=~/models/OLMoE-1B-7B-0125-Instruct
echo "== $(date -u +%FT%TZ) smoke: quiet gate"
QW=$(bash allquiet746.sh 1 5400 </dev/null); echo "qw=$QW"
export CUDA_VISIBLE_DEVICES=1
rm -f out/SMOKE_C.json out/SMOKE_C.trace.jsonl out/SMOKE_A.json out/SMOKE_A.trace.jsonl out/SMOKE.txt
env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
  MOEI_EXP753_TRACE=1 MOEI_EXP753_TRACE_FILE=/home/mfeth/exp753/out/SMOKE_C.trace.jsonl \
  timeout 1500 python3 engine_arm753.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
  --threads 4 --gpu-route on --prompts prompts_smoke.json --max-new 64 --warmup 1 --arm-name C --timing on \
  --out out/SMOKE_C.json > out/SMOKE_C.log 2>&1 </dev/null
RC1=$?
QW=$(bash allquiet746.sh 1 5400 </dev/null); echo "qw2=$QW"
env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
  timeout 1500 python3 engine_arm753.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
  --threads 4 --gpu-route on --prompts prompts_smoke.json --max-new 64 --warmup 1 --arm-name A --timing off \
  --out out/SMOKE_A.json > out/SMOKE_A.log 2>&1 </dev/null
RC2=$?
python3 - "$RC1" "$RC2" <<'PY'
import json, sys, os
rc1, rc2 = int(sys.argv[1]), int(sys.argv[2])
ok = [f"rc_smokeC={rc1}", f"rc_smokeA={rc2}"]
allok = (rc1 == 0 and rc2 == 0)
ref = json.load(open('refs/engine_ref.json'))
for cell in ('SMOKE_C', 'SMOKE_A'):
    try:
        d = json.load(open(f'out/{cell}.json'))
        for i in (0, 1):
            m = d['rows'][i]['out_ids'] == ref['out_ids'][i]
            ok.append(f"parity_{cell}_p{i}={m}"); allok &= m
        txt = open(f'out/{cell}.log').read()
        arm = 'C' if cell.endswith('C') else 'A'
        want = f"exp753 mode={arm} trace={'1' if arm=='C' else '0'} timing={'on' if arm=='C' else 'off'}"
        b = want in txt; ok.append(f"banner_{cell}={b}"); allok &= b
        if arm == 'C':
            tsf = d.get('timing_setter_found'); ok.append(f"timing_setter={tsf}"); allok &= bool(tsf)
    except Exception as e:
        ok.append(f"load_{cell}=ERR:{e!r}"); allok = False
tp = 'out/SMOKE_C.trace.jsonl'
if os.path.exists(tp):
    with open(tp) as f:
        meta = json.loads(f.readline())
        sites = {}
        enter = exitid = 0
        for ln in f:
            try: r = json.loads(ln)
            except Exception: continue
            sites[r['s']] = sites.get(r['s'], 0) + 1
            if r['s'] == 1: enter += 1
            if r['s'] == 2 and r['e'] >= 0: exitid += 1
    ok.append(f"meta_records={meta.get('records')}")
    ok.append(f"dropped={meta.get('dropped')}")
    ok.append(f"kern15={sites.get(15, 0)}")
    ok.append(f"si_enter={enter} si_exitid={exitid}")
    allok &= meta.get('records', 0) > 0 and meta.get('dropped', -1) == 0 and sites.get(15, 0) > 0 and enter == exitid
    allok &= all(sites.get(s, 0) > 0 for s in list(range(1, 15)) + list(range(16, 22)))
else:
    ok.append("smokeC_trace=MISSING"); allok = False
if os.path.exists('out/SMOKE_A.trace.jsonl'):
    ok.append("smokeA_trace=UNEXPECTED-EXISTS"); allok = False
else:
    ok.append("smokeA_trace=absent")
verdict = "SMOKE-PASS" if allok else "SMOKE-FAIL"
open('out/SMOKE.txt', 'w').write(verdict + " " + " ".join(ok) + "\n")
print(verdict, *ok, sep="\n")
PY
echo "== $(date -u +%FT%TZ) smoke done"
