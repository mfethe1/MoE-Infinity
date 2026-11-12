cd /home/mfeth/exp795
E=/home/mfeth/moei-engine/MoE-Infinity/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
B=$E.d252620b.bak
cp -n $E $B
cp /home/mfeth/exp795/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so $E
sha256sum $E | cut -c1-16 > probe799.out
M=~/models/OLMoE-1B-7B-0125-Instruct; O=~/moe-offload; PF=/home/mfeth/exp788/probe8.json
PY=~/venvs/moei-engine/bin/python
uptime >> probe799.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DECODE=1 $PY /home/mfeth/exp794/probe794.py --model $M --offload $O --prompts $PF --ratio 0.5 --out /home/mfeth/exp795/p799_W.json >> probe799.out 2>&1
echo ARM-W RC=$? >> probe799.out; uptime >> probe799.out
for I in 1 2 3 4 5; do
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DECODE=1 MOE_INLINE_WAIT=0 $PY /home/mfeth/exp794/probe794.py --model $M --offload $O --prompts $PF --ratio 0.5 --out /home/mfeth/exp795/p799_F$I.json >> probe799.out 2>&1
echo ARM-F$I RC=$? >> probe799.out; uptime >> probe799.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DECODE=1 $PY /home/mfeth/exp794/probe794.py --model $M --offload $O --prompts $PF --ratio 0.5 --out /home/mfeth/exp795/p799_N$I.json >> probe799.out 2>&1
echo ARM-N$I RC=$? >> probe799.out; uptime >> probe799.out
done
cp $B $E
sha256sum $E | cut -c1-16 >> probe799.out
echo ALL-DONE >> probe799.out
