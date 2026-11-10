#!/bin/bash
# run_exp764b.sh — sample-count extension for exp764 (INCONCLUSIVE 21056 < 30000 frozen gate).
# Identical protocol/filenames+suffix 2; collapsed stacks APPENDED; frozen analyze764.py re-run as-is.
cd /home/mfeth/exp764 || exit 1; source ~/venvs/moei-engine/bin/activate; export CUDA_VISIBLE_DEVICES=1
M=~/models/OLMoE-1B-7B-0125-Instruct
PY=$(command -v py-spy) || exit 4
while pgrep -f 'engine_arm76[0-9]\.py' >/dev/null; do sleep 30; done
run_cell(){ local ID=$1 SP=$2 SO=$3 OP=$4
  [ -s out/$ID.json ] && { echo "skip $ID"; return 0; }
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp759/src753 MOEI_EXP752_MODE=RC \
      MOE_INFINITY_PROFILE_IO=1 MOE_INFINITY_PROFILE_IO_OUT=/home/mfeth/exp764/out/$ID.io.jsonl \
      timeout 1500 $PY record -r 100 -f raw -o out/$ID.pyspy -- python3 engine_arm764.py --model $M \
      --offload ~/moe-offload --policy lcnu --ratio 0.75 --threads 4 --gpu-route off \
      --spec-prefetch $SP --spec-overlap $SO --overlap-policy $OP \
      --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null
  echo "$ID RC=$?"; grep -E "DONE" out/$ID.log | tail -1 | cut -c1-120
}
run_cell PROF_LGC2  off off off
run_cell PROF_SPEC2 on  off off
cat out/PROF_LGC2.pyspy >> out/PROF_LGC.pyspy
cat out/PROF_SPEC2.pyspy >> out/PROF_SPEC.pyspy
sha256sum out/PROF_LGC.pyspy out/PROF_SPEC.pyspy >> FREEZE-764.txt
echo "extension $(date -u +%FT%TZ): appended repeat 2" >> FREEZE-764.txt
python3 analyze764.py out > out/verdict.txt 2>&1; echo "analyzer rc=$?"
cat out/verdict.txt
