#!/bin/bash
# exp751 runner (rented native-Linux container, single GPU 0). Serial. Phase A = exp747 micro2.py unchanged (host-callback stall);
# Phase B = exp746 arms unchanged (hf / engine gpu-route on / off, quiet). No CI runners or Ollama exist here; the analyzer still
# applies the pre-start GPU-memory and load rules. Spinner PIDs are recorded and only those are killed.
cd /root/exp751; source /root/venv/bin/activate; mkdir -p out
export PATH=/root/venv/bin:/usr/local/cuda/bin:$PATH
M=/root/models/OLMoE-1B-7B-0125-Instruct; G=0
echo "== $(date -u +%FT%TZ) start"
sha256sum micro2.py engine_arm.py hf_arm.py nvsamp.py prompts.json cells.json analyze.py run_exp751.sh setup751.sh model.sha256 > out/RUN_SHA256
{ python3 -c "import torch;print(torch.__version__, torch.version.cuda)"; nproc; uname -r; lscpu | grep -E "Model name"; free -g | head -2
  nvidia-smi --query-gpu=index,name,driver_version,memory.total,pcie.link.gen.max,pcie.link.width.max,pcie.link.gen.current --format=csv,noheader
  cat /proc/1/cgroup | head -3; [ -e /proc/sys/fs/binfmt_misc/WSLInterop ] && echo WSL || echo NOT-WSL; } > out/ENV.txt 2>&1
quiet(){ local t0=$(date +%s) m; while :; do m=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  awk '{exit !($1<3.0)}' /proc/loadavg && [ "$m" -le 1024 ] && { echo "$(( $(date +%s)-t0 )) QUIET"; return; }
  [ $(( $(date +%s)-t0 )) -ge 600 ] && { echo "$(( $(date +%s)-t0 )) TIMEOUT"; return; }; sleep 10; done; }
mon(){ while :; do n=0; [ -s "$2" ] && n=$(xargs -r ps -o pid= -p < "$2" 2>/dev/null | wc -l)
  ps_=$(awk '/^some/{split($2,a,"=");print a[2]}' /proc/pressure/cpu 2>/dev/null); echo "$(date +%T) $(cut -d' ' -f1 /proc/loadavg) 0 ${ps_:-NA} $n" >> "$1"; sleep 2; done; }
PIDF=""
spin(){ local k; : > $PIDF; for k in $(seq 1 $1); do bash -c 'while :; do :; done' </dev/null >/dev/null 2>&1 & echo $! >> $PIDF; done; }
unspin(){ [ -n "$PIDF" ] && [ -s "$PIDF" ] && { kill $(cat $PIDF) 2>/dev/null; sleep 1; kill -9 $(cat $PIDF) 2>/dev/null; }; true; }
trap unspin EXIT
precell(){ local qw mg; qw=$(quiet); mg=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  echo "$1,$qw,$mg,$(cut -d' ' -f1 /proc/loadavg)" >> out/precell.csv
  [ "$mg" -gt 1024 ] && { echo "$1" >> out/FLAGGED; echo "$1 pre-start gpu=$mg" >> out/FLAGGED.why; }; true; }
# ---- prep (not a cell): build the engine offload store once so no cell pays conversion
if [ ! -s /root/moe-offload/model_signature.json ]; then
  echo "== $(date -u +%FT%TZ) prep offload"
  CUDA_VISIBLE_DEVICES=$G timeout 3000 python3 engine_arm.py --model $M --offload /root/moe-offload --policy lcnu --ratio 0.75 --threads 4 \
     --gpu-route on --prompts prep_prompts.json --max-new 8 --warmup 1 --out out/prep.json > out/prep.log 2>&1 </dev/null; echo "prep RC=$?"
fi
while read -u 3 ID ARM K; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  PIDF=out/$ID.spinpids; : > $PIDF
  precell $ID
  mon out/$ID.load $PIDF & MP=$!
  if [ "$ARM" = micro ]; then
    [ "$K" -gt 0 ] && spin $K; sleep 30
    echo "== $(date -u +%FT%TZ) $ID spin=$K"
    CUDA_VISIBLE_DEVICES=$G timeout 900 python3 micro2.py out/$ID.json 1500 > out/$ID.log 2>&1 </dev/null; RC=$?
  else
    python3 nvsamp.py $G out/$ID.util.csv 0.05 </dev/null & SP=$!; sleep 10
    echo "== $(date -u +%FT%TZ) $ID arm=$ARM"
    case $ARM in
      hf) CUDA_VISIBLE_DEVICES=$G timeout 1800 python3 hf_arm.py --model $M --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
      on|off) CUDA_VISIBLE_DEVICES=$G env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE timeout 1800 python3 engine_arm.py --model $M \
           --offload /root/moe-offload --policy lcnu --ratio 0.75 --threads 4 --gpu-route $ARM --prompts prompts.json --max-new 64 --warmup 1 \
           --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    esac; RC=$?; sleep 3; kill $SP 2>/dev/null; wait $SP 2>/dev/null
  fi
  unspin; sleep 2; kill $MP 2>/dev/null; wait $MP 2>/dev/null
  echo "$ID RC=$RC"; [ $RC -ne 0 ] && { tail -8 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done 3< <(python3 -c "import json;[print(c['id'],c['arm'],c.get('spin',0)) for c in json.load(open('cells.json'))]")
python3 analyze.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP751-DONE"; touch out/DONE
