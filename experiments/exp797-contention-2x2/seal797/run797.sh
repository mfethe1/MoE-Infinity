cd /home/mfeth/exp795
E=/home/mfeth/moei-engine/MoE-Infinity/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
B=$E.d252620b.bak
cp -n $E $B
cp /home/mfeth/exp795/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so $E
sha256sum $E | cut -c1-16 > probe797.out
M=~/models/OLMoE-1B-7B-0125-Instruct; O=~/moe-offload; PF=/home/mfeth/exp788/probe8.json
PY=~/venvs/moei-engine/bin/python
burn(){ rm -f /tmp/burn797.pids; for i in 0 1 2 3; do taskset -c $i bash -c 'while :; do :; done' & echo $! >> /tmp/burn797.pids; done; sleep 1; }
noburn(){ kill $(cat /tmp/burn797.pids) 2>/dev/null; sleep 1; }
for REP in 1 2 3; do
  uptime >> probe797.out; CUDA_VISIBLE_DEVICES=1 $PY probe795.py --model $M --offload $O --prompts $PF --ratio 0.5 --out p797_SQ$REP.json >> probe797.out 2>&1; echo ARM-SQ$REP RC=$? >> probe797.out; uptime >> probe797.out
  burn; CUDA_VISIBLE_DEVICES=1 MOE_INLINE_WAIT=0 $PY probe795.py --model $M --offload $O --prompts $PF --ratio 0.5 --out p797_PB$REP.json >> probe797.out 2>&1; echo ARM-PB$REP RC=$? >> probe797.out; noburn
  uptime >> probe797.out; CUDA_VISIBLE_DEVICES=1 $PY probe795.py --model $M --offload $O --prompts $PF --ratio 0.5 --out p797_SB$REP.json >> probe797.out 2>&1; echo ARM-SB$REP RC=$? >> probe797.out; uptime >> probe797.out
  burn; CUDA_VISIBLE_DEVICES=1 MOE_INLINE_WAIT=0 $PY probe795.py --model $M --offload $O --prompts $PF --ratio 0.5 --out p797_PQ$REP.json >> probe797.out 2>&1; echo ARM-PQ$REP RC=$? >> probe797.out; noburn
done
cp $B $E
sha256sum $E | cut -c1-16 >> probe797.out
echo ALL-DONE >> probe797.out
