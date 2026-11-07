#!/bin/bash
# exp751 native-Linux bring-up on a rented vast.ai container (image nvidia/cuda:12.8.1-devel-ubuntu24.04).
# Mirrors Winnie's moei-engine venv (setup.sh/rebuild.sh, pip freeze 2026-11-07): torch 2.11.0+cu128, MoE-Infinity 0337988 + Winnie's local
# 22-line grouped_moe_prefill.cu diff, moe-store 096f51f9, CUTLASS 954c8d7b, transformers 5.22.1. Idempotent stages; logs to /root/exp751/setup.log.
set -uo pipefail
W=/root/exp751; cd $W; LOG=$W/setup.log
log(){ echo "$(date -u +%FT%TZ) $*" | tee -a $LOG; }
die(){ log "FATAL $*"; echo FAILED > $W/SETUP_STATUS; exit 1; }
log START nproc=$(nproc)
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq python3-venv python3-dev git uuid-dev curl tmux procps >/dev/null 2>&1 || die apt
log APT-OK $(python3 --version)
[ -x /root/venv/bin/python ] || python3 -m venv /root/venv || die venv
P=/root/venv/bin; export PATH=$P:/usr/local/cuda/bin:$PATH CUDA_HOME=/usr/local/cuda
$P/pip install -q -U pip "setuptools==81.0.0" "setuptools-scm==10.3.4" wheel==0.48.0 ninja==1.13.2 py-cpuinfo==9.0.0 "huggingface_hub==2.4.0" cmake==4.4.4 >>$LOG 2>&1 || die tools
log TOOLS-OK
( HF_HUB_ENABLE_HF_TRANSFER=1 $P/hf download allenai/OLMoE-1B-7B-0125-Instruct \
    --local-dir /root/models/OLMoE-1B-7B-0125-Instruct > $W/download.log 2>&1; echo "DL-EXIT=$?" >> $W/download.log ) &
DLPID=$!
$P/pip install -q torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128 >>$LOG 2>&1 || die torch
$P/python -c "import torch;print('TORCH',torch.__version__,torch.version.cuda,torch.cuda.is_available(),torch.cuda.get_device_name(0),torch.cuda.get_device_capability(0))" >>$LOG 2>&1 || die torch-import
log TORCH-OK
$P/pip install -q --no-deps -r $W/requirements-pinned.txt >>$LOG 2>&1 || die reqs
$P/pip install -q --no-deps "sglang-kernel==0.4.6.post1" "moe-store @ git+https://github.com/EfficientMoE/moe-store.git@096f51f92ca9d698907d9a79120a7819ea094266" >>$LOG 2>&1 || die moestore
log REQS-OK
if [ ! -d /root/cutlass ]; then git clone -q https://github.com/NVIDIA/cutlass.git /root/cutlass && git -C /root/cutlass checkout -q $(cat $W/cutlass.commit) || die cutlass; fi
log "CUTLASS $(git -C /root/cutlass rev-parse --short HEAD)"
if [ ! -d /root/MoE-Infinity ]; then git clone -q https://github.com/EfficientMoE/MoE-Infinity.git /root/MoE-Infinity || die clone; fi
cd /root/MoE-Infinity && git checkout -q 033798811664f5d89cae58049ff16e912ebc5862 || die checkout
git diff --quiet && { git apply $W/winnie-local.diff || die diff-apply; }
log "SRC $(git rev-parse --short HEAD) diff-lines=$(git diff | wc -l)"
MOE_ENABLE_SM120=1 MOE_ENABLE_SM90=0 CUTLASS_DIR=/root/cutlass MAX_JOBS=16 $P/pip install --no-build-isolation --no-deps -e . > $W/build.log 2>&1 || { tail -30 $W/build.log >> $LOG; die build; }
log BUILD-OK
cd /root && $P/python -c "from moe_infinity import MoE; import moe_infinity; print('IMPORT-OK', moe_infinity.__file__)" >>$LOG 2>&1 || die import
log IMPORT-OK
wait $DLPID; tail -2 $W/download.log >> $LOG; grep -q "DL-EXIT=0" $W/download.log || die download
du -sh /root/models/OLMoE-1B-7B-0125-Instruct >> $LOG
( cd /root/models/OLMoE-1B-7B-0125-Instruct && sha256sum -c $W/model.sha256 ) >>$LOG 2>&1 || die model-sha-mismatch-vs-winnie
log MODEL-SHA-OK
mkdir -p $W/out; $P/pip freeze > $W/out/pip-freeze.txt 2>&1
log DONE; echo OK > $W/SETUP_STATUS
