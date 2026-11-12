cd /home/mfeth/exp795
E=/home/mfethe/../mfeth/moei-engine/MoE-Infinity/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
E=/home/mfeth/moei-engine/MoE-Infinity/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
B=$E.d252620b.bak
cp -n $E $B
cp /home/mfeth/exp795/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so $E
sha256sum $E | cut -c1-16 > probe798b.out
M=~/models/OLMoE-1B-7B-0125-Instruct; O=~/moe-offload; PF=/home/mfeth/exp788/probe8.json
PY=~/venvs/moei-engine/bin/python
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DECODE=1 $PY /home/mfeth/exp794/probe794.py --model $M --offload $O --prompts $PF --ratio 0.5 --out /home/mfeth/exp795/p798_W.json >> probe798b.out 2>&1
echo ARM-W RC=$? >> probe798b.out; uptime >> probe798b.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DECODE=1 MOE_INLINE_WAIT=0 $PY /home/mfeth/exp794/probe794.py --model $M --offload $O --prompts $PF --ratio 0.5 --out /home/mfeth/exp795/p798_F1.json >> probe798b.out 2>&1
echo ARM-F1 RC=$? >> probe798b.out; uptime >> probe798b.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DECODE=1 $PY /home/mfeth/exp794/probe794.py --model $M --offload $O --prompts $PF --ratio 0.5 --out /home/mfeth/exp795/p798_N1.json >> probe798b.out 2>&1
echo ARM-N1 RC=$? >> probe798b.out; uptime >> probe798b.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DECODE=1 MOE_INLINE_WAIT=0 $PY /home/mfeth/exp794/probe794.py --model $M --offload $O --prompts $PF --ratio 0.5 --out /home/mfeth/exp795/p798_F2.json >> probe798b.out 2>&1
echo ARM-F2 RC=$? >> probe798b.out; uptime >> probe798b.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DECODE=1 $PY /home/mfeth/exp794/probe794.py --model $M --offload $O --prompts $PF --ratio 0.5 --out /home/mfeth/exp795/p798_N2.json >> probe798b.out 2>&1
echo ARM-N2 RC=$? >> probe798b.out; uptime >> probe798b.out
cp $B $E
sha256sum $E | cut -c1-16 >> probe798b.out
echo ALL-DONE >> probe798b.out
