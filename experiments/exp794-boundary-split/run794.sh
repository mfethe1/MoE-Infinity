cd /home/mfeth/exp794
for R in 0.25 0.5; do
  export MOE_GROUPED_DECODE=1
  CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python probe794.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --prompts /home/mfeth/exp788/probe8.json --ratio $R --out /home/mfeth/exp794/p794_$R.json >> /home/mfeth/exp794/probe794.out 2>&1
  echo ARM-$R RC=$? >> /home/mfeth/exp794/probe794.out
done
echo ALL-DONE >> /home/mfeth/exp794/probe794.out
