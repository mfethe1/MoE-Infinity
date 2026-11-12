cd /home/mfeth/exp790
export MOE_GROUPED_DECODE=1
CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python profile790d.py \
  --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload \
  --prompts /home/mfeth/exp788/probe8.json --out /home/mfeth/exp790/p790e.json \
  > /home/mfeth/exp790/profile790e.out 2>&1
echo RC=$? >> /home/mfeth/exp790/profile790e.out
