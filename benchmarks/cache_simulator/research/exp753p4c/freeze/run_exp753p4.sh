#!/bin/bash
# exp753p4c runner (Winnie, WSL). Serial; one model process at a time; GPU1 only.
# Adapted from exp753 run_exp753.sh (sealed, sha 00233144) with ONLY:
#   (1) engine cells get --force-steps (PREREG-P4C.md §3); (2) work dir ~/exp753p4
#   (sealed ~/exp753 untouched); (3) RUN_SHA256 covers this tree + the SAME private
#   build (/home/mfeth/exp753/src) + FREEZE; (4) post-run FORCE_CHECK.txt provenance
#   gate (PREREG-P4C.md §5 G-M addition, computed here, frozen with the run).
# Arms: hf (HF reference, UNCHANGED), A (engine, tracer dormant), B (+timeline trace),
# C (+compute-timing hook, KERN samples), G (CUDA-graph capture feasibility probe).
# Engine arms load the PRIVATE build (PYTHONPATH=/home/mfeth/exp753/src). All engine
# arms: lcnu, ratio 0.75, gpu-route on, threads 4.
cd ~/exp753p4; source ~/venvs/moei-engine/bin/activate; mkdir -p out
busy(){ local u; for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753build exp753smoke; do systemctl --user is-active -q $u && return 0; done; return 1; }
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) exp753p4c start"
[ -e out/RUN_SHA256 ] && mv out/RUN_SHA256 out/RUN_SHA256.prev-$(date -u +%H%M%S)
sha256sum allquiet746.sh mon753.sh nvsamp.py engine_arm753_p4.py hf_arm.py graph_probe.py prompts.json cells.json \
  analyze753.py run_exp753p4.sh smoke753p4.sh PREREG-P4C.md FREEZE \
  /home/mfeth/exp753/src_patched/expert_dispatcher.cpp /home/mfeth/exp753/infra753.inc \
  /home/mfeth/exp753/src/moe_infinity/_store*.so \
  /home/mfeth/exp753/src/moe_infinity/engine/generation_loop.py \
  /home/mfeth/exp753/src/moe_infinity/entrypoints/big_modeling.py \
  refs/engine_ref.json refs/hf_ref.json > out/RUN_SHA256
PYTHONPATH=/home/mfeth/exp753/src python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei', moe_infinity.__file__, s.__file__)" > out/ENV.txt 2>&1
git -C /home/mfeth/exp753/src rev-parse HEAD >> out/ENV.txt 2>&1; nproc >> out/ENV.txt; /usr/lib/wsl/lib/nvidia-smi -L >> out/ENV.txt
M=~/models/OLMoE-1B-7B-0125-Instruct
while read -u 3 ID ARM K G; do
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  QW=$(bash allquiet746.sh $G 5400 </dev/null)
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  FA=$(/usr/lib/wsl/lib/nvidia-smi --query-compute-apps=pid --format=csv,noheader | sort -u | grep -c .)
  LA=$(cut -d' ' -f1 /proc/loadavg); RW=$(pgrep -fc Runner.Worker)
  echo "$ID,$QW,$MG,$OL,$LA,$RW,$FA" >> out/precell.csv
  # Pre-committed covariate thresholds (exp753 PREREG §10h, reused verbatim):
  BADCOV=""
  { [ "$MG" -gt 1024 ] || [ "$OL" -ne 0 ] || [ "$RW" -ge 1 ] || [ "$FA" -ge 1 ] || \
    awk -v l="$LA" 'BEGIN{exit !(l+0>=8)}'; } && BADCOV="cov"
  [ -n "$BADCOV" ] && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG ollama=$OL la=$LA rw=$RW fa=$FA" >> out/FLAGGED.why; }
  bash mon753.sh $G out/FLAGGED $ID </dev/null & MP=$!
  python3 nvsamp.py $G out/$ID.util.csv 0.05 </dev/null & SP=$!; sleep 10
  export CUDA_VISIBLE_DEVICES=$G
  echo "== $(date -u +%FT%TZ) $ID arm=$ARM gpu=$G qw=$QW la=$LA foreign_any=$FA"
  case $ARM in
    hf) timeout 1800 python3 hf_arm.py --model $M --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    A) env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
       timeout 1800 python3 engine_arm753_p4.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
       --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --arm-name A --timing off \
       --force-steps --out out/$ID.json > out/$ID.log 2>&1 </dev/null ;;
    B|C) T=off; [ "$ARM" = C ] && T=on
       env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
       MOEI_EXP753_TRACE=1 MOEI_EXP753_TRACE_FILE=/home/mfeth/exp753p4/out/$ID.trace.jsonl \
       timeout 1800 python3 engine_arm753_p4.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
       --threads 4 --gpu-route on --prompts prompts.json --max-new 64 --warmup 1 --arm-name $ARM --timing $T \
       --force-steps --out out/$ID.json > out/$ID.log 2>&1 </dev/null
       [ -s out/$ID.trace.jsonl ] && head -1 out/$ID.trace.jsonl > out/$ID.tracemeta ;;
    G) timeout 1200 env -u MOE_INFINITY_UNVALIDATED_HW -u MOE_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp753/src \
       python3 graph_probe.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 --threads 4 \
       --gpu-route on --prompts prompts.json --max-new 64 --out out/g_probe.json > out/g_probe.log 2>&1 </dev/null ;;
  esac
  RC=$?; sleep 3; kill $MP $SP 2>/dev/null; wait $MP $SP 2>/dev/null
  pkill -f "graph_probe.py --step" 2>/dev/null; true  # orphan sweep if timeout fired
  # Review F5(i) fail-fast: forced engine rows must all be n_new==64 (fail-closed detection
  # of a stale/unflipped engine object); recorded, never silently continued.
  if [ "$ARM" != hf ] && [ "$ARM" != G ]; then
    python3 - "$ID" >> out/FORCED-LEN-CHECK.txt 2>&1 <<'PY'
import json, os, sys
cid = sys.argv[1]
p = f"out/{cid}.json"
if os.path.exists(p):
    r = json.load(open(p))
    lens = [row.get("n_new") for row in r.get("rows", [])]
    if lens != [64] * 6:
        print(f"FORCED-LEN-ANOMALY {cid}: row_lens={lens}")
        open("out/ANOMALY", "a").write(f"{cid} FORCED-LEN-ANOMALY {lens}\n")
    else:
        print(f"{cid}: forced-len OK {lens}")
else:
    print(f"FORCED-LEN-ANOMALY {cid}: json missing")
PY
  fi
  echo "$ID RC=$RC"
  [ "$ARM" != G ] && grep -E "exp753 mode=|exp753p4c force-steps|prompt [0-9]:" out/$ID.log | tail -8 | cut -c1-200
  [ $RC -ne 0 ] && { tail -8 out/${ARM:+$ID}.log 2>/dev/null; echo "$ID FAILED" >> out/FAILED; }
done 3< <(python3 -c "import json;[print(c['id'],c['arm'],c['stress'],c['gpu']) for c in json.load(open('cells.json'))]")
python3 analyze753.py out refs > out/verdict.txt 2>&1; cat out/verdict.txt
# PREREG-P4C.md §5 G-M addition (frozen with the run): force_steps provenance gate.
python3 - > out/FORCE_CHECK.txt 2>&1 <<'PY'
import json, os
ok = True
for cid in ("a_1", "a_2", "b_1", "b_2", "c_1", "c_2"):
    p = f"out/{cid}.json"
    if not os.path.exists(p):
        print(f"{cid}: MISSING"); ok = False; continue
    r = json.load(open(p))
    fs = r.get("force_steps")
    good = (isinstance(fs, dict) and fs.get("eos_before") == 50279 and fs.get("eos_after") == -1
            and fs.get("row_lens") == [64] * 6)
    print(f"{cid}: force_steps={fs} -> {'OK' if good else 'BAD'}")
    ok &= good
for cid in ("hf_1", "hf_2"):
    p = f"out/{cid}.json"
    if os.path.exists(p):
        r = json.load(open(p))
        good = r.get("force_steps") is None
        print(f"{cid}: force_steps absent -> {'OK' if good else 'BAD'}")
        ok &= good
print("FORCE-CHECK:", "PASS" if ok else "FAIL")
PY
grep FORCE-CHECK out/FORCE_CHECK.txt
echo "== $(date -u +%FT%TZ) EXP753P4C-DONE"
