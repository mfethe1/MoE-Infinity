#!/bin/bash
# exp767 runner (Winnie, WSL): py-spy --native stack attribution, 2 profiled cells
# (NAT_LGC, NAT_SPEC). Derived VERBATIM from frozen run_exp764.sh (e8bc3f79) with
# additive changes only, documented per lane discipline:
#   1. paths exp764 -> exp767, cell IDs PROF_* -> NAT_*
#   2. py-spy record gains --native (the exp767 measurement)
#   3. banner grep corrected to the RESOLVED int (exp764 SETTLEMENT: env alias RC
#      prints mode=2; verified against sealed exp764 out/*.log before freeze)
#   4. busy-gate unit list adds exp767
# Same envelope/build/flags as exp762/exp764 cells (src753 @ b7f6ca4); observation-only.
cd /home/mfeth/exp767 || exit 1; source ~/venvs/moei-engine/bin/activate; mkdir -p out
export CUDA_VISIBLE_DEVICES=1
M=~/models/OLMoE-1B-7B-0125-Instruct
PY=$(command -v py-spy) || { echo "PYSPY-FAIL: py-spy not on PATH"; exit 4; }
# busy gate (same classes as exp762/exp764; our own cmdline excluded)
busy(){ local u p c
  for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753 exp753p4 exp753p4build exp755 exp756build exp756build2 exp759build exp761 exp761run exp762 exp766 exp767; do
    systemctl --user is-active -q $u 2>/dev/null && return 0; done
  for p in $(pgrep -f '/home/mfethe/exp7[0-9][0-9]/run_exp7[0-9][0-9]\\.sh' 2>/dev/null) $(pgrep -f 'engine_arm76[0-9]\\.py' 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
    case "$c" in *exp767*) continue ;; esac
    [ -n "$c" ] && return 0; done
  return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
git -C /home/mfeth/exp759/src753 rev-parse HEAD > out/SRC_HEAD.txt 2>&1
PYTHONPATH=/home/mfeth/exp759/src753 python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei-RC753', moe_infinity.__file__, s.__file__); print('torch', torch.__version__)" > out/ENV.txt 2>&1
grep -q "^moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py" out/ENV.txt && grep -q " /home/mfeth/exp759/src753/moe_infinity/_store\\." out/ENV.txt \
  || { echo "IDENTITY-FAIL: build is not /home/mfeth/exp759/src753"; cat out/ENV.txt; exit 9; }
$PY --version > out/PYSPY.txt 2>&1
run_cell(){ # ID SP SO OP
  local ID=$1 SP=$2 SO=$3 OP=$4
  [ -s out/$ID.json ] && { echo "skip $ID"; return 0; }
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp759/src753 MOEI_EXP752_MODE=RC \
      MOE_INFINITY_PROFILE_IO=1 MOE_INFINITY_PROFILE_IO_OUT=/home/mfeth/exp767/out/$ID.io.jsonl \
      timeout 1500 $PY record --native -r 100 -f raw -o out/$ID.pyspy -- python3 engine_arm767.py --model $M \
      --offload ~/moe-offload --policy lcnu --ratio 0.75 --threads 4 --gpu-route off \
      --spec-prefetch $SP --spec-overlap $SO --overlap-policy $OP \
      --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null
  local RC=$?
  echo "$ID RC=$RC"
  grep -q "exp752 mode=2" out/$ID.log || echo "$ID banner-absent" >> out/BANNER-FAIL
  [ -s out/$ID.pyspy ] || { echo "$ID pyspy-empty RC=$RC" >> out/BADIO; }
  grep -E "prompt [0-9]:|DONE" out/$ID.log | tail -3 | cut -c1-160
}
run_cell NAT_LGC  off off off
run_cell NAT_SPEC on  off off
echo "== done $(date -u +%FT%TZ) =="
