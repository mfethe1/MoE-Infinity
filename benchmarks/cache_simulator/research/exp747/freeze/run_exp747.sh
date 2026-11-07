#!/bin/bash
# exp747 runner (Winnie, WSL). Model-free; serial; GPU1. Starts after lane-79990 unit exp746 (and exp740-744) are inactive.
# Spinners are bash busy loops; their PIDs are recorded in out/ID.spinpids and only those PIDs are ever killed.
cd ~/exp747; source ~/venvs/moei-engine/bin/activate; mkdir -p out
busy(){ local u; for u in exp740 exp741 exp742 exp743 exp744 exp746; do systemctl --user is-active -q $u && return 0; done; return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
sha256sum allquiet.sh mon2.sh micro2.py cells.json analyze.py run_exp747.sh > out/RUN_SHA256
{ python3 -c "import torch;print(torch.__version__, torch.version.cuda)"; nproc; uname -r; /usr/lib/wsl/lib/nvidia-smi --query-gpu=index,name,driver_version --format=csv,noheader; } > out/ENV.txt 2>&1
PIDF=""
spin(){ local k; : > $PIDF; for k in $(seq 1 $1); do bash -c 'while :; do :; done' </dev/null >/dev/null 2>&1 & echo $! >> $PIDF; done; }
unspin(){ [ -n "$PIDF" ] && [ -s "$PIDF" ] && { kill $(cat $PIDF) 2>/dev/null; sleep 1; kill -9 $(cat $PIDF) 2>/dev/null; }; true; }
trap unspin EXIT
while read -u 3 ID K G; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  PIDF=out/$ID.spinpids; : > $PIDF
  QW=$(bash allquiet.sh $G 5400 </dev/null)
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  echo "$ID,$K,$QW,$MG,$OL,$(cut -d' ' -f1 /proc/loadavg),$(pgrep -fc Runner.Worker)" >> out/precell.csv
  { [ "$MG" -gt 1024 ] || [ "$OL" -ne 0 ]; } && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG ollama=$OL" >> out/FLAGGED.why; }
  bash mon2.sh $G out/$ID.mon $PIDF </dev/null & MP=$!
  [ "$K" -gt 0 ] && spin $K; sleep 30
  echo "== $(date -u +%FT%TZ) $ID spin=$K qw=$QW"
  CUDA_VISIBLE_DEVICES=$G timeout 900 python3 micro2.py out/$ID.json 1500 > out/$ID.log 2>&1 </dev/null
  RC=$?; unspin; sleep 2; kill $MP 2>/dev/null; wait $MP 2>/dev/null
  echo "$ID RC=$RC"; grep -E "^(hostfn_stall|kern_sync)" out/$ID.log | cut -c1-160
  [ $RC -ne 0 ] && { tail -8 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
done 3< <(python3 -c "import json;[print(c['id'],c['spin'],c['gpu']) for c in json.load(open('cells.json'))]")
python3 analyze.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP747-DONE"
