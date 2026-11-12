cd /home/mfeth/exp793
export MOE_GROUPED_DECODE=1
CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python profile793.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --prompts /home/mfeth/exp788/probe8.json --ratio 0.5 --out /home/mfeth/exp793/p793.json > /home/mfeth/exp793/profile793.out 2>&1
echo RC=$? >> /home/mfeth/exp793/profile793.out
