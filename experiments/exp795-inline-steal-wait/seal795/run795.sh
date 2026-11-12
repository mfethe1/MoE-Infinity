cd /home/mfeth/exp795
E=/home/mfeth/moei-engine/MoE-Infinity/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
B=$E.d252620b.bak
CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python probe795.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --prompts /home/mfeth/exp788/probe8.json --ratio 0.5 --out /home/mfeth/exp795/p795_C.json >> /home/mfeth/exp795/probe795.out 2>&1
echo ARM-C RC=$? >> /home/mfeth/exp795/probe795.out
cp -n $E $B
cp /home/mfeth/exp795/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so $E
MOE_INLINE_WAIT=0 CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python probe795.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --prompts /home/mfeth/exp788/probe8.json --ratio 0.5 --out /home/mfeth/exp795/p795_P.json >> /home/mfeth/exp795/probe795.out 2>&1
echo ARM-P RC=$? >> /home/mfeth/exp795/probe795.out
CUDA_VISIBLE_DEVICES=1 ~/venvs/moei-engine/bin/python probe795.py --model ~/models/OLMoE-1B-7B-0125-Instruct --offload ~/moe-offload --prompts /home/mfeth/exp788/probe8.json --ratio 0.5 --out /home/mfeth/exp795/p795_A.json >> /home/mfeth/exp795/probe795.out 2>&1
echo ARM-A RC=$? >> /home/mfeth/exp795/probe795.out
cp $B $E
sha256sum $E | cut -c1-16 >> /home/mfeth/exp795/probe795.out
echo ALL-DONE >> /home/mfeth/exp795/probe795.out
