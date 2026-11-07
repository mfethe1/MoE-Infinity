#!/bin/bash
# exp752 build: private copy of Winnie's engine tree (0337988 + local grouped_moe_prefill.cu diff) + exp752 patch; rebuilds ONLY moe_infinity._store (expert_dispatcher lives there) in place.
# Never touches ~/moei-engine or the shared venv's install.
set -u; S=/home/mfeth/exp752/src; L=/home/mfeth/exp752/build.log; P=/home/mfeth/venvs/moei-engine/bin
log(){ echo "$(date -u +%FT%TZ) $*" >> $L; }
log START
if [ ! -d $S/.git ]; then rsync -a --exclude build/ /home/mfeth/moei-engine/MoE-Infinity/ $S/ || { log RSYNC-FAIL; exit 1; }; fi
cd $S; log "HEAD $(git rev-parse --short HEAD) dirty=$(git status --short | wc -l)"
sha256sum core/parallel/expert_dispatcher.cpp core/parallel/expert_dispatcher.h >> $L
cp /home/mfeth/exp752/src_patched/expert_dispatcher.cpp /home/mfeth/exp752/src_patched/expert_dispatcher.h core/parallel/
sha256sum core/parallel/expert_dispatcher.cpp core/parallel/expert_dispatcher.h >> $L
export CPATH=/home/mfeth/local/usr/include:/opt/nvidia/nsight-systems/2024.6.2/target-linux-x64/nvtx/include LIBRARY_PATH=/home/mfeth/local/usr/lib/x86_64-linux-gnu
export CUDA_HOME=/usr/local/cuda-12.8 PATH=$P:/usr/local/cuda-12.8/bin:$PATH MOE_ENABLE_SM120=1 MOE_ENABLE_SM90=0 CUTLASS_DIR=/home/mfeth/cutlass MAX_JOBS=8
cat > /home/mfeth/exp752/only_engine.py <<'PY'
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
nice -n 5 $P/python /home/mfeth/exp752/only_engine.py > /home/mfeth/exp752/build_ext.log 2>&1; RC=$?; log "BUILD RC=$RC"
cd /home/mfeth && PYTHONPATH=$S $P/python -c "import torch, moe_infinity, moe_infinity._store as e; print('IMPORT', moe_infinity.__file__, e.__file__)" >> $L 2>&1
sha256sum $S/moe_infinity/_store*.so /home/mfeth/moei-engine/MoE-Infinity/moe_infinity/_store*.so >> $L
log DONE
