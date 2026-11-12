cd /home/mfeth/exp791
for R in 0.25 0.5 0.75 0.9; do
  CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python probe791.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --prompts /home/mfeth/exp788/probe8.json --ratio $R --out /home/mfeth/exp791/p791_$R.json >> /home/mfeth/exp791/probe791.out 2>&1
  echo ARM-$R RC=$? >> /home/mfeth/exp791/probe791.out
done
echo ALL-DONE >> /home/mfeth/exp791/probe791.out
