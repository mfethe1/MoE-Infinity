#!/bin/bash
# exp728 runner (Winnie). Serial GPU use: waits for exp724..exp727. Builds the patched tree, then runs cells.json.
cd ~/exp728; source ~/venvs/moei-engine/bin/activate; mkdir -p out
w=0; while systemctl --user is-active -q exp724 || systemctl --user is-active -q exp725 || systemctl --user is-active -q exp726 || systemctl --user is-active -q exp727; do
  w=$((w+1)); [ $w -gt 1080 ] && { echo "ABORT waited 18h"; exit 8; }; sleep 60; done
echo "== $(date -u +%FT%TZ) start"
sha256sum AMENDMENT1.md engine_arm.py fixrun.py fix.patch prompts.json cells.json analyze.py run_exp728.sh > out/RUN_SHA256
U=~/moei-engine/MoE-Infinity
( cd $U; echo "UNPATCHED $(git rev-parse --short HEAD)"; git status --porcelain | grep -v '^??' ; git diff --stat ) > out/unpatched_tree.txt
if [ ! -s ~/moei-fix728/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so ]; then
  [ -d ~/moei-fix728 ] || git -C $U worktree add -q --detach ~/moei-fix728 0337988
  cd ~/moei-fix728 && git apply ~/exp728/fix.patch && git diff --stat > ~/exp728/out/fix_tree.txt
  export CPATH=~/local/usr/include:/opt/nvidia/nsight-systems/2024.6.2/target-linux-x64/nvtx/include LIBRARY_PATH=~/local/usr/lib/x86_64-linux-gnu
  export CUDA_HOME=/usr/local/cuda-12.8 PATH=~/venvs/moei-engine/bin:/usr/local/cuda-12.8/bin:$PATH
  echo "== $(date -u +%FT%TZ) build"
  MOE_ENABLE_SM120=1 MOE_ENABLE_SM90=0 CUTLASS_DIR=~/cutlass MAX_JOBS=12 timeout 7200 python setup.py build_ext --inplace > ~/exp728/out/build.log 2>&1
  echo "BUILD_RC=$?" | tee -a ~/exp728/out/build_rc.txt
  cd ~/exp728
fi
[ -s ~/moei-fix728/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so ] || { echo "BUILD-FAILED"; python3 analyze.py out > out/verdict.txt 2>&1; cat out/verdict.txt; exit 9; }
NS=/usr/lib/wsl/lib/nvidia-smi
# AMENDMENT1: Ollama answers on 127.0.0.1 from WSL (gateway IP refuses); probe failure -> -1 (fail-closed, flagged)
oll(){ local o; o=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && { grep -o '"name"' <<<"$o" | wc -l; } || echo -1; }
mon(){ while [ -e out/.cell ]; do echo "$(date -u +%FT%TZ),$(cat out/.cell),$($NS --query-gpu=index,memory.used --format=csv,noheader,nounits | tr '\n' ';'),$(oll)" >> out/monitor.csv; sleep 5; done; }
python3 -c "import json;[print(c['id'],c['build'],c['gpus'],c['ratio']) for c in json.load(open('cells.json'))]" |
while read ID B GPUS RAT; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  echo "$ID,$($NS --query-gpu=index,memory.used --format=csv,noheader,nounits | tr '\n' ';'),$(oll)" >> out/precell.csv
  echo "== $(date -u +%FT%TZ) $ID build=$B gpus=$GPUS r=$RAT"
  echo $ID > out/.cell; mon & MP=$!
  if [ $B = P ]; then RUNNER="fixrun.py"; else RUNNER="engine_arm.py"; fi
  CUDA_VISIBLE_DEVICES=$GPUS timeout 1800 python3 $RUNNER --model ~/models/OLMoE-1B-7B-0125-Instruct \
    --offload ~/moe-offload --policy lcnu --ratio $RAT --prompts prompts.json --max-new 64 --warmup 1 \
    --out out/$ID.json > out/$ID.log 2>&1
  RC=$?; rm -f out/.cell; wait $MP; echo "$ID,$RC" >> out/rc.csv; echo "$ID RC=$RC"
  [ $RC -ne 0 ] && tail -2 out/$ID.log
done
python3 analyze.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP728-DONE"
