cd /home/mfeth/exp791
mkdir -p /home/mfeth/exp792 && cp probe791.py /home/mfeth/exp792/probe792.py
cd /home/mfeth/exp792
for R in 0.40 0.50 0.60 0.70; do
  CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python probe792.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --prompts /home/mfeth/exp788/probe8.json --ratio $R --out /home/mfeth/exp792/p792_$R.json >> /home/mfeth/exp792/probe792.out 2>&1
  echo ARM-$R RC=$? >> /home/mfeth/exp792/probe792.out
done
echo ALL-DONE >> /home/mfeth/exp792/probe792.out
sha256sum probe792.py | cut -c1-16 >> /home/mfeth/exp792/probe792.out
