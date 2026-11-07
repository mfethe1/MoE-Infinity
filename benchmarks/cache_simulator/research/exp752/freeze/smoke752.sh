#!/bin/bash
# exp752 untimed smoke (NOT part of the timed run): 2 prompts x 16 tokens per mode on GPU1, checks banner + no crash + token parity.
cd ~/exp752; source ~/venvs/moei-engine/bin/activate; mkdir -p smoke
bash allquiet746.sh 1 1800 > smoke/qw.txt
for A in H R RC; do
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp752/src MOEI_EXP752_MODE=$A CUDA_VISIBLE_DEVICES=1 \
    timeout 900 python3 engine_arm.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --policy lcnu --ratio 0.75 \
    --threads 4 --gpu-route on --prompts smoke_prompts.json --max-new 16 --warmup 1 --out smoke/$A.json > smoke/$A.log 2>&1 </dev/null
  echo "$A RC=$?" >> smoke/rc.txt
done
python3 - >> smoke/rc.txt <<'PY'
import json
d={a:json.load(open(f"smoke/{a}.json")) for a in ("H","R","RC")}
ids={a:[r.get("out_ids") for r in d[a]["rows"]] for a in d}
print("parity R==H", ids["R"]==ids["H"], "RC==H", ids["RC"]==ids["H"])
for a in d: print(a, [round(r["decode_tok_s"],2) for r in d[a]["rows"]], d[a].get("gpu_route_effective"))
PY
echo SMOKE-DONE >> smoke/rc.txt
