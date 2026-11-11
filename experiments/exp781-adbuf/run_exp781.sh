#!/bin/bash
# exp781: async-dbuf (EXP773_DB=1) vs blocking topk (unset) — manual-loop decode.
# Single variable: EXP773_DB env flag (selects async double-buffered topk copy
# vs blocking .indices.cpu() in expert_prefetcher.speculative_prefetch).
# attempt-2 runner: env options MUST precede NAME=VALUE assignments (attempt-1
# cell PY_BLOCK died RC=127: "-u EXP773_DB" after assignments was taken as the
# command). Cells are now explicit.
set -u
cd /home/mfeth/exp781
mkdir -p out
exec > >(tee -a out/unit.log) 2>&1
echo "== $(date -u +%FT%TZ) start"
for f in /proc/[0-9]*; do
  c=$(tr '\0' ' ' < $f/cmdline 2>/dev/null)
  case "$c" in *engine_arm78[01]*|*run_exp77[4-9]*|*run_exp78[01]*)
    if [ "$f" != "/proc/$$" ]; then echo "BUSY: $c"; exit 5; fi;; esac
done
SRC=/home/mfeth/exp776/src776
PY=$HOME/venvs/moei-engine/bin/python
MODEL=$HOME/models/OLMoE-1B-7B-0125-Instruct
OFFLOAD=$HOME/moe-offload
sha256sum $SRC/moe_infinity/memory/expert_prefetcher.py | cut -c1-16 > out/SRC776_FILE_SHA.txt
git -C /home/mfeth/exp759/src753 rev-parse HEAD 2>/dev/null > out/SRC_HEAD.txt
$PY -c "import torch,transformers; print('torch', torch.__version__); print('tf', transformers.__version__)" > out/ENV.txt
echo "moei-776 $SRC/moe_infinity" >> out/ENV.txt
sha256sum engine_arm781.py | cut -c1-16 > out/ENGB_SHA.txt
: > out/CELL_RC.txt

run_engine () {  # $1 = out tag; remaining args form the full command line
  local TAG=$1; shift
  "$@" > out/$TAG.log 2>&1
  local RC=$?
  echo "$TAG RC=$RC" | tee -a out/CELL_RC.txt
}

# cell A: async double buffer (EXP773_DB=1)
run_engine PY_ADBUF \
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE \
  PYTHONPATH=$SRC MOEI_EXP752_MODE=RC CUDA_VISIBLE_DEVICES=1 EXP773_DB=1 \
  $PY engine_arm781.py --model $MODEL --offload $OFFLOAD \
  --policy lcnu --ratio 0.75 --threads 4 --gpu-route off \
  --spec-prefetch on --spec-overlap off --overlap-policy off \
  --prompts /home/mfeth/exp776/prompts774.json --max-new 64 --warmup 1 \
  --out out/PY_ADBUF.json

# cell B: blocking topk (EXP773_DB explicitly unset, options BEFORE assignments)
run_engine PY_BLOCK \
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE -u EXP773_DB \
  PYTHONPATH=$SRC MOEI_EXP752_MODE=RC CUDA_VISIBLE_DEVICES=1 \
  $PY engine_arm781.py --model $MODEL --offload $OFFLOAD \
  --policy lcnu --ratio 0.75 --threads 4 --gpu-route off \
  --spec-prefetch on --spec-overlap off --overlap-policy off \
  --prompts /home/mfeth/exp776/prompts774.json --max-new 64 --warmup 1 \
  --out out/PY_BLOCK.json

grep -q "exp781 db=1 ok=True" out/PY_ADBUF.log || : > out/BANNER-FAIL
grep -q "exp781 db=0 ok=True" out/PY_BLOCK.log || : > out/BANNER-FAIL
for t in PY_ADBUF PY_BLOCK; do [ -f out/$t.json ] || : > out/BANNER-FAIL; done
echo "== done $(date -u +%FT%TZ) =="
