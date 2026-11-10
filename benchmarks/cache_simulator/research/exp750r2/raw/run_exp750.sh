#!/bin/bash
# exp750 runner (Winnie). Derived from run_exp749.sh. Differences (PREREG):
#  1. NO build step: the three _store .so files (unpatched ~/moei-engine, ~/moei-fix740, ~/moei-fix749) must
#     hash-equal ref/exp749_so_sha_post.txt; the runner aborts otherwise.
#  2. Arms R1/S1/S0/P2/K2/C2/H2 (cells750.json, 21 cells). Per-cell CUDA_LAUNCH_BLOCKING from the cell's clb
#     field ("1" only for K2); out/<id>.env records CUDA_LAUNCH_BLOCKING and CUDA_DEVICE_ORDER.
#  3. Per-cell PCIe link snapshot in out/link.csv. No exp742 dependency; reference is ref/exp749_b1_R.json.
#  4. After the 21 cells: one rerun pass for FOREIGN/TIMED-DRIFT/TIMER-INVALID cells (id suffix _x), then
#     classify750.py. Timeouts: H 1800, U 2400, F/P 3600, K2 5400 (CLB may be slow).
# Launched as one-shot `systemd-run --user --unit exp750`.
cd ~/exp750 || exit 5; source ~/venvs/moei-engine/bin/activate; mkdir -p out
[ -e out/rc.csv ] && { echo "ABORT out/rc.csv exists (no silent re-run into a used out/)"; exit 6; }
[ -s FROZEN750.sha256 ] && sha256sum -c --quiet FROZEN750.sha256 || { echo "ABORT FROZEN750.sha256 missing or mismatch"; exit 15; }
unset CUDA_LAUNCH_BLOCKING
busy(){ systemctl --user list-units --no-legend --state=active,activating 'exp7*' | grep -v 'exp750\.service' | grep -q .; }
w=0; while busy; do
  w=$((w+1)); [ $w -gt 480 ] && { echo "ABORT waited 8h"; exit 8; }; sleep 60; done
echo "== $(date -u +%FT%TZ) start (waited ${w} min for other exp7* units)"
env | grep -E '^(CUDA_|OMP_|MKL_|OPENBLAS_|TORCH|PYTORCH_|NCCL_|NVIDIA_|LD_LIBRARY_PATH|PATH|VIRTUAL_ENV|PYTHON|TOKENIZERS_|HF_HUB_OFFLINE|TRANSFORMERS_OFFLINE)' | grep -v -i -E 'token=|key=|secret' | sort > out/env_start.txt  # A2/review NIT 9: allowlisted env snapshot (audit only, no secrets)
sha256sum PREREG.md quietwait.sh engine_arm750.py hf_arm750.py fixrun750.py prompts.json cells750.json gen_cells750.py classify750.py run_exp750.sh FROZEN750.sha256 ref/exp749_so_sha_post.txt ref/exp749_b1_R.json > out/RUN_SHA256
U=~/moei-engine/MoE-Infinity
( cd $U; echo "UNPATCHED $(git rev-parse --short HEAD)"; git status --porcelain | grep -v '^??' ; git diff --stat ) > out/unpatched_tree.txt
SO=$U/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
SO740=~/moei-fix740/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
SO749=~/moei-fix749/moe_infinity/_store.cpython-312-x86_64-linux-gnu.so
check_so(){ local ref; ref=$(grep "$2" ref/exp749_so_sha_post.txt | cut -d' ' -f1)
  [ -s "$1" ] && [ -n "$ref" ] && [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$ref" ] || { echo "ABORT .so missing or sha256 != ref/exp749_so_sha_post.txt: $1"; exit 12; }; }
check_so $SO 'moei-engine/MoE-Infinity/'
check_so $SO740 'moei-fix740/'
check_so $SO749 'moei-fix749/'
sha256sum $SO $SO740 $SO749 > out/so_sha_pre.txt
MI=$(python3 -c "import moe_infinity;print(moe_infinity.__file__)" 2>/dev/null | tail -1)
case "$MI" in "$HOME"/moei-engine/*) echo "R moe_infinity=$MI" > out/r_provenance.txt;;
  *) echo "ABORT venv moe_infinity not under ~/moei-engine: $MI"; exit 10;; esac
for T in $U ~/moei-fix740 ~/moei-fix749; do
  grep -q '_native_generation_engine' $T/moe_infinity/entrypoints/big_modeling.py &&
    grep -q 'def _sample(self, logits' $T/moe_infinity/engine/generation_loop.py ||
    { echo "ABORT native _sample path missing in $T"; exit 11; }
done
NS=/usr/lib/wsl/lib/nvidia-smi
oll(){ local o; o=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && { grep -o '"name"' <<<"$o" | wc -l; } || echo -1; }
echo "$(date -u +%FT%TZ) ollama_loaded_models=$(oll) (-1 = API unreachable)" > out/ollama_preflight.txt
mon(){ while [ -e out/.cell ]; do echo "$(date -u +%FT%TZ),$(cat out/.cell),$($NS --query-gpu=index,memory.used --format=csv,noheader,nounits | tr '\n' ';'),$(oll)" >> out/monitor.csv; sleep 5; done; }
MODEL=~/models/OLMoE-1B-7B-0125-Instruct
run_cell(){ local ID=$1 B=$2 GPUS=$3 RAT=$4 CLB=$5 ARM=$6 QW TO RC MP RUNNER TREE
  [ -s out/$ID.json ] && { echo "skip $ID"; return; }
  QW=$(bash quietwait.sh "$GPUS" 5400 < /dev/null); echo "$ID,$QW" >> out/quietwait.csv
  case "$QW" in *TIMEOUT*) echo "$ID,SKIP-NOTQUIET" >> out/rc.csv; echo "$ID SKIP-NOTQUIET ($QW)"; return;; esac
  echo "$ID,$($NS --query-gpu=index,memory.used --format=csv,noheader,nounits | tr '\n' ';'),$(oll)" >> out/precell.csv
  echo "$ID,$($NS --query-gpu=index,pcie.link.gen.current,pcie.link.width.current --format=csv,noheader,nounits | tr '\n' ';')" >> out/link.csv
  if [ $ARM = K2 ]; then TO=5400; elif [ $B = H ]; then TO=1800; elif [ $B = U ]; then TO=2400; else TO=3600; fi
  echo "== $(date -u +%FT%TZ) $ID build=$B gpus=$GPUS r=$RAT CUDA_LAUNCH_BLOCKING=${CLB:-unset} timeout=$TO"
  if [ "$CLB" = "1" ]; then EV=(env CUDA_LAUNCH_BLOCKING=1); else EV=(env -u CUDA_LAUNCH_BLOCKING); fi
  echo $ID > out/.cell; mon & MP=$!
  if [ $B = H ]; then
    CUDA_VISIBLE_DEVICES=$GPUS "${EV[@]}" bash -c '{ echo "CUDA_LAUNCH_BLOCKING=${CUDA_LAUNCH_BLOCKING-}"; echo "CUDA_DEVICE_ORDER=${CUDA_DEVICE_ORDER-}"; } > "$0"; exec "$@"' out/$ID.env \
      timeout $TO python3 hf_arm750.py --model $MODEL \
      --prompts prompts.json --max-new 64 --warmup 1 --timed-reps 3 --out out/$ID.json > out/$ID.log 2>&1 < /dev/null
  else
    case $B in F) RUNNER=fixrun750.py; TREE=~/moei-fix749;; P) RUNNER=fixrun750.py; TREE=~/moei-fix740;;
      *) RUNNER=engine_arm750.py; TREE=;; esac
    MOEI_FIX_TREE=$TREE MOEI_DEVICE_DIAG=0 CUDA_VISIBLE_DEVICES=$GPUS "${EV[@]}" bash -c '{ echo "CUDA_LAUNCH_BLOCKING=${CUDA_LAUNCH_BLOCKING-}"; echo "CUDA_DEVICE_ORDER=${CUDA_DEVICE_ORDER-}"; } > "$0"; exec "$@"' out/$ID.env \
      timeout $TO python3 $RUNNER --model $MODEL \
      --offload ~/moe-offload --policy lcnu --ratio $RAT --prompts prompts.json --max-new 64 --warmup 1 --timed-reps 3 \
      --out out/$ID.json > out/$ID.log 2>&1 < /dev/null
  fi
  RC=$?; rm -f out/.cell; wait $MP; echo "$ID,$RC" >> out/rc.csv; echo "$ID RC=$RC"
  [ $RC -ne 0 ] && tail -2 out/$ID.log; :; }
while read -u 3 ID B GPUS RAT CLB ARM; do
  [ "$CLB" = "-" ] && CLB=""; run_cell "$ID" "$B" "$GPUS" "$RAT" "$CLB" "$ARM"
done 3< <(python3 -c "import json;[print(c['id'],c['build'],c['gpus'],c['ratio'],c['clb'] or '-',c['arm']) for c in json.load(open('cells750.json'))]")
for ID in $(python3 classify750.py out --list-reruns); do
  read B GPUS RAT CLB ARM < <(python3 -c "import json,sys;c=[x for x in json.load(open('cells750.json')) if x['id']==sys.argv[1]][0];print(c['build'],c['gpus'],c['ratio'],c['clb'] or '-',c['arm'])" $ID); [ "$CLB" = "-" ] && CLB=""
  echo "== rerun $ID as ${ID}_x (build=$B gpus=$GPUS r=$RAT clb=$CLB arm=$ARM)"
  run_cell "${ID}_x" "$B" "$GPUS" "$RAT" "$CLB" "$ARM"
done
sha256sum $SO $SO740 $SO749 > out/so_sha_post.txt
python3 classify750.py out ref/exp749_b1_R.json > out/class750.txt 2>&1; echo "classify750 rc=$?" >> out/class750.txt; cat out/class750.txt
echo "== $(date -u +%FT%TZ) EXP750-DONE"
