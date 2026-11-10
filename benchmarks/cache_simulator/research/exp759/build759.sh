#!/bin/bash
# exp759 build: private copy of Winnie's engine tree, reset to pristine, then checked out at OUR PR #353 head
# b7f6ca4 short-sha prefix (retire-by-event + completion queue, MOEI_EXP752_MODE ladder). Rebuilds ONLY moe_infinity._store
# in place at /home/mfeth/exp759/src753. Never touches ~/moei-engine, the shared venv install, exp752/src or exp756/src.
set -u; S=/home/mfeth/exp759/src753; L=/home/mfeth/exp759/build.log; P=/home/mfeth/venvs/moei-engine/bin
# head is b7f6ca4 (short sha of PR #353 head); checkout by prefix, gate via rev-parse case below
log(){ echo "$(date -u +%FT%TZ) $*" >> $L; }
log START
if [ ! -d $S/.git ]; then rsync -a --exclude build/ /home/mfeth/moei-engine/MoE-Infinity/ $S/ || { log RSYNC-FAIL; exit 1; }; fi
cd $S || { log "CD-FAIL $S"; exit 7; }
git reset --hard HEAD >/dev/null 2>&1
git fetch --no-tags https://github.com/EfficientMoE/MoE-Infinity.git refs/pull/353/head || { log FETCH-FAIL; exit 2; }
git checkout --detach b7f6ca4 >/dev/null 2>&1 || { log CHECKOUT-FAIL; exit 3; }
GOT=$(git rev-parse HEAD)
log "HEAD $GOT dirty=$(git status --short | wc -l)"
case "$GOT" in b7f6ca4*) ;; *) log "HEAD-MISMATCH got=$GOT want=b7f6ca4*"; exit 4;; esac
[ "$(git status --short | wc -l)" = "0" ] || { log "DIRTY-TREE"; exit 5; }
sha256sum core/parallel/expert_dispatcher.cpp core/parallel/expert_dispatcher.h >> $L
# sealed-envelope build-env compile fix (nvcc 12.8 + GCC 13), byte-same diff as exp752/exp756 builds;
# PR #353 did not touch extensions/kernel/grouped_moe_prefill.cu.
git apply /home/mfeth/exp756/grouped_moe_prefill_local.diff || { log "LOCALDIFF-APPLY-FAIL"; exit 6; }
sha256sum extensions/kernel/grouped_moe_prefill.cu >> $L
export CPATH=/home/mfeth/local/usr/include:/opt/nvidia/nsight-systems/2024.6.2/target-linux-x64/nvtx/include LIBRARY_PATH=/home/mfeth/local/usr/lib/x86_64-linux-gnu
export CUDA_HOME=/usr/local/cuda-12.8 PATH=$P:/usr/local/cuda-12.8/bin:$PATH MOE_ENABLE_SM120=1 MOE_ENABLE_SM90=0 CUTLASS_DIR=/home/mfeth/cutlass MAX_JOBS=8
cat > /home/mfeth/exp759/only_engine.py <<'PY'
import setuptools, sys
_orig = setuptools.setup
def _only(**kw):
    kw["ext_modules"] = [e for e in kw["ext_modules"] if e.name == "moe_infinity._store"]
    assert len(kw["ext_modules"]) == 1
    return _orig(**kw)
setuptools.setup = _only
sys.argv = ["setup.py", "build_ext", "--inplace"]
import os
exec(compile(open("setup.py").read(), os.path.abspath("setup.py"), "exec"), {"__file__": os.path.abspath("setup.py"), "__name__": "__main__"})
PY
nice -n 5 $P/python /home/mfeth/exp759/only_engine.py > /home/mfeth/exp759/build_ext.log 2>&1; RC=$?; log "BUILD RC=$RC"
cd /home/mfeth && PYTHONPATH=$S $P/python -c "import torch, moe_infinity, moe_infinity._store as e; print('IMPORT', moe_infinity.__file__, e.__file__)" >> $L 2>&1
sha256sum $S/moe_infinity/_store*.so /home/mfeth/exp752/src/moe_infinity/_store*.so /home/mfeth/exp756/src/moe_infinity/_store*.so >> $L
grep -q "IMPORT /home/mfeth/exp759/src753" $L || { log "IDENTITY-FAIL import path"; exit 8; }
[ $RC -eq 0 ] || exit 9
log DONE
