cd /home/mfeth/exp795
E=/home/mfeth/moei-engine/MoE-Infinity/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
B=$E.d252620b.bak
cp -n $E $B
cp /home/mfeth/exp795/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so $E
sha256sum $E | cut -c1-16 > probe796.out
M=~/models/OLMoE-1B-7B-0125-Instruct; O=~/moe-offload; P=/home/mfeth/exp788/probe8.json
PY=~/venvs/moei-engine/bin/python
CUDA_VISIBLE_DEVICES=1 MOE_INLINE_WAIT=0 $PY probe795.py --model $M --offload $O --prompts $P --ratio 0.5 --out p796_P1.json >> probe796.out 2>&1; echo ARM-P1 RC=$? >> probe796.out
CUDA_VISIBLE_DEVICES=1 MOE_INLINE_WAIT=0 $PY probe795.py --model $M --offload $O --prompts $P --ratio 0.5 --out p796_P2.json >> probe796.out 2>&1; echo ARM-P2 RC=$? >> probe796.out
CUDA_VISIBLE_DEVICES=1 MOE_INLINE_WAIT=0 MOE_GROUPED_DETERMINISTIC=1 $PY probe795.py --model $M --offload $O --prompts $P --ratio 0.5 --out p796_DP1.json >> probe796.out 2>&1; echo ARM-DP1 RC=$? >> probe796.out
CUDA_VISIBLE_DEVICES=1 MOE_INLINE_WAIT=0 MOE_GROUPED_DETERMINISTIC=1 $PY probe795.py --model $M --offload $O --prompts $P --ratio 0.5 --out p796_DP2.json >> probe796.out 2>&1; echo ARM-DP2 RC=$? >> probe796.out
CUDA_VISIBLE_DEVICES=1 MOE_INLINE_WAIT=0 MOE_GROUPED_DETERMINISTIC=1 $PY probe795.py --model $M --offload $O --prompts $P --ratio 0.5 --out p796_DP3.json >> probe796.out 2>&1; echo ARM-DP3 RC=$? >> probe796.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DETERMINISTIC=1 $PY probe795.py --model $M --offload $O --prompts $P --ratio 0.5 --out p796_DA1.json >> probe796.out 2>&1; echo ARM-DA1 RC=$? >> probe796.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DETERMINISTIC=1 $PY probe795.py --model $M --offload $O --prompts $P --ratio 0.5 --out p796_DA2.json >> probe796.out 2>&1; echo ARM-DA2 RC=$? >> probe796.out
CUDA_VISIBLE_DEVICES=1 MOE_GROUPED_DETERMINISTIC=1 $PY probe795.py --model $M --offload $O --prompts $P --ratio 0.5 --out p796_DA3.json >> probe796.out 2>&1; echo ARM-DA3 RC=$? >> probe796.out
cp $B $E
sha256sum $E | cut -c1-16 >> probe796.out
echo ALL-DONE >> probe796.out
