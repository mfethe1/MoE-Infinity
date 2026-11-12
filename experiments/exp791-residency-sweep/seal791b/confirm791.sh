cd /home/mfeth/exp791
for R in 0.25 0.5; do
  for REP in 1 2 3; do
    CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python probe791.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --prompts /home/mfeth/exp788/probe8.json --ratio $R --out /home/mfeth/exp791/p791c_${R}_r${REP}.json >> /home/mfeth/exp791/confirm791.out 2>&1
    echo CONF-$R-r$REP RC=$? >> /home/mfeth/exp791/confirm791.out
  done
done
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader -i 0 >> /home/mfeth/exp791/confirm791.out
echo CONF-DONE >> /home/mfeth/exp791/confirm791.out
