#!/bin/bash
# exp762 runner (Winnie, WSL). Serial; one model process at a time; GPU1 only.
# Engine-level speculative prefetch overlap A/B (io_overlap direction): 4 arms x n=3 interleaved.
#   LGC  = speculative_prefetch=False (legacy reactive serial baseline)
#   SPEC = speculative_prefetch=True, speculative_prefetch_overlap=False (prefetch fires AFTER barrier)
#   OVR  = speculative_prefetch=True, speculative_prefetch_overlap=True, policy=off (fires BEFORE barrier)
#   ENF  = OVR + overlap_prefetch_policy=enforce (budgeted overlap-window byte admission)
# Build: OUR PR #353 head b7f6ca4 (/home/mfeth/exp759/src753, MOEI_EXP752_MODE=RC) for ALL arms —
# same build as exp759/exp760; only config differs. gpu-route OFF in all arms (held fixed:
# ArcherConfig.__post_init__ raises on explicit gpu_only_expert_routing=True combined with
# overlap modes, and gpu-route is a separately measured factor (exp744), not under test here).
# Envelope identical to exp759: OLMoE-1B-7B-0125-Instruct, lcnu 0.75, ~/moe-offload, 6 prompts x 64 tok
# greedy, warmup 1, threads 4. MOE_INFINITY_PROFILE_IO=1 in ALL arms incl. LGC.
cd ~/exp762 || exit 1; source ~/venvs/moei-engine/bin/activate; mkdir -p out
busy(){ local u p c
  for u in exp746 exp747 exp748 exp749 exp750 exp752build exp753 exp753p4 exp753p4build exp755 exp756build exp756build2 exp759build exp761 exp761run exp762; do
    systemctl --user is-active -q $u 2>/dev/null && return 0; done
  for p in $(pgrep -f '/home/mfethe/exp7[0-9][0-9]/run_exp7[0-9][0-9]\.sh' 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
    case "$c" in *exp762*) continue ;; esac
    [ -n "$c" ] && return 0; done
  return 1; }
# (busy covers systemd units AND detached foreign runner scripts, e.g. tier1's exp761 CG3 rerun
#  of 2026-11-10T20:17Z which ran outside its unit; our own run_exp762.sh cmdline is excluded)
while busy; do sleep 60; done
echo "== $(date -u +%FT%TZ) start"
[ -e out/RUN_SHA256 ] && mv out/RUN_SHA256 out/RUN_SHA256.prev-$(date -u +%H%M%S)
sha256sum allquiet746.sh mon752.sh nvsamp.py engine_arm762.py prompts.json cells762.json analyze762.py run_exp762.sh \
  /home/mfeth/exp759/src753/moe_infinity/_store*.so > out/RUN_SHA256
git -C /home/mfeth/exp759/src753 rev-parse HEAD > out/SRC_HEAD.txt 2>&1
PYTHONPATH=/home/mfeth/exp759/src753 python3 -c "import torch, moe_infinity, moe_infinity._store as s;print('moei-RC753', moe_infinity.__file__, s.__file__); print('torch', torch.__version__)" > out/ENV.txt 2>&1
grep -q "^moei-RC753 /home/mfeth/exp759/src753/moe_infinity/__init__.py" out/ENV.txt && grep -q " /home/mfeth/exp759/src753/moe_infinity/_store\." out/ENV.txt \
  || { echo "IDENTITY-FAIL: build is not /home/mfeth/exp759/src753"; cat out/ENV.txt; exit 9; }
# PREFLIGHT: ArcherConfig must expose the overlap subsystem (fail-closed NO-RUN)
PYTHONPATH=/home/mfeth/exp759/src753 python3 - > out/PREFLIGHT.txt 2>&1 <<'PYEOF'
import dataclasses
from moe_infinity.utils.config import ArcherConfig
names = {f.name for f in dataclasses.fields(ArcherConfig)}
need = {"speculative_prefetch", "speculative_prefetch_overlap", "overlap_prefetch_policy",
        "overlap_prefetch_ewma_alpha", "overlap_prefetch_safety_factor",
        "overlap_prefetch_max_window_bytes", "overlap_prefetch_max_inflight_bytes"}
missing = need - names
print("OVERLAP_PREFLIGHT:", "PASS" if not missing else f"MISSING {sorted(missing)}")
PYEOF
grep -q "OVERLAP_PREFLIGHT: PASS" out/PREFLIGHT.txt || { echo "NO-RUN: overlap subsystem absent from build"; cat out/PREFLIGHT.txt; exit 8; }
M=~/models/OLMoE-1B-7B-0125-Instruct
G=1
while read -u 3 ID ARM SP SO OP; do
  # fail-closed cell-config validation (exp762 attempt-2 lesson: flag/pid name collision
  # passed a pid as --spec-prefetch; every cell died at argparse. Config vars must be literal)
  case "$ARM" in LGC|SPEC|OVR|ENF) ;; *) echo "$ID BADCFG-arm:$ARM" >> out/FAILED; continue;; esac
  case "$SP" in on|off) ;; *) echo "$ID BADCFG-spec_prefetch:$SP" >> out/FAILED; continue;; esac
  case "$SO" in on|off) ;; *) echo "$ID BADCFG-spec_overlap:$SO" >> out/FAILED; continue;; esac
  case "$OP" in off|observe|enforce) ;; *) echo "$ID BADCFG-overlap_policy:$OP" >> out/FAILED; continue;; esac
  [ -s out/$ID.json ] && { echo "skip $ID"; continue; }
  QW=$(bash allquiet746.sh $G 5400 </dev/null)
  O=$(curl -sf -m 2 http://127.0.0.1:11434/api/ps) && OL=$(grep -o '"name"' <<<"$O" | wc -l) || OL=-1
  MG=$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $G | tr -d ' ')
  FA=$(/usr/lib/wsl/lib/nvidia-smi --query-compute-apps=pid --format=csv,noheader | sort -u | grep -c .)
  LA=$(cut -d' ' -f1 /proc/loadavg); RW=$(pgrep -fc Runner.Worker)
  echo "$ID,$QW,$MG,$OL,$LA,$RW,$FA" >> out/precell.csv
  { [ "$MG" -gt 1024 ] || [ "$OL" -ne 0 ]; } && { echo "$ID" >> out/FLAGGED; echo "$ID pre-start gpu=$MG ollama=$OL" >> out/FLAGGED.why; }
  bash mon752.sh $G out/FLAGGED $ID </dev/null & MP=$!
  python3 nvsamp.py $G out/$ID.util.csv 0.05 </dev/null & SMP=$!; sleep 10
  export CUDA_VISIBLE_DEVICES=$G
  echo "== $(date -u +%FT%TZ) $ID arm=$ARM sp=$SP so=$SO op=$OP gpu=$G qw=$QW la=$LA foreign_any=$FA"
  env -u MOE_INFINITY_UNVALIDATED_HW -u MOEI_GROUPED_DECODE PYTHONPATH=/home/mfeth/exp759/src753 MOEI_EXP752_MODE=RC \
      MOE_INFINITY_PROFILE_IO=1 MOE_INFINITY_PROFILE_IO_OUT=/home/mfeth/exp762/out/$ID.io.jsonl \
      timeout 1800 python3 engine_arm762.py --model $M --offload ~/moe-offload --policy lcnu --ratio 0.75 \
      --threads 4 --gpu-route off --spec-prefetch $SP --spec-overlap $SO --overlap-policy $OP \
      --prompts prompts.json --max-new 64 --warmup 1 --out out/$ID.json > out/$ID.log 2>&1 </dev/null
  RC=$?; sleep 3; kill $MP $SMP 2>/dev/null; wait $MP $SMP 2>/dev/null
  echo "$ID RC=$RC"; grep -E "exp752 mode=|prompt [0-9]:|DONE" out/$ID.log | tail -8 | cut -c1-200
  grep -q "exp752 mode=RC" out/$ID.log || { echo "$ID" >> out/BANNER-FAIL; echo "$ID banner absent (exp752 mode=RC)" >> out/BANNER-FAIL.why; }
  { [ -s out/$ID.io.jsonl ] || [ -s out/$ID.io.json ]; } || echo "$ID io-profile-empty" >> out/BADIO
  [ $RC -ne 0 ] && { tail -8 out/$ID.log; echo "$ID FAILED" >> out/FAILED; }
  [ $RC -eq 0 ] && [ -s out/$ID.json ] && [ -f out/FAILED ] && sed -i "/^$ID /d" out/FAILED
  sleep 20
done 3< <(python3 -c "import json;[print(c['id'],c['arm'],c['spec_prefetch'],c['spec_overlap'],c['overlap_policy']) for c in json.load(open('cells762.json'))]")
python3 analyze762.py out > out/verdict.txt 2>&1; cat out/verdict.txt
echo "== $(date -u +%FT%TZ) EXP762-DONE"
