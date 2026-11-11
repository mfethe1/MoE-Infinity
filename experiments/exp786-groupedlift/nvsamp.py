#!/usr/bin/env python3
"""exp743 GPU-busy sampler. Usage: nvsamp.py GPU_INDEX OUT.csv [PERIOD_S]. Runs until killed.
Writes `epoch_s,util_gpu_pct,mem_used_mib` lines via NVML (ctypes, WSL libnvidia-ml). NVML utilization.gpu =
percent of the driver's last sample period during which >=1 kernel was executing on the device (any process)."""
import ctypes, sys, time

lib = None
for p in ("/usr/lib/wsl/lib/libnvidia-ml.so.1", "libnvidia-ml.so.1"):
    try:
        lib = ctypes.CDLL(p); break
    except OSError:
        pass
assert lib is not None, "libnvidia-ml not found"


class Util(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class Mem(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


assert lib.nvmlInit_v2() == 0
h = ctypes.c_void_p()
assert lib.nvmlDeviceGetHandleByIndex_v2(int(sys.argv[1]), ctypes.byref(h)) == 0
period = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
u, m = Util(), Mem()
with open(sys.argv[2], "a", buffering=1) as f:
    while True:
        t = time.time()
        if lib.nvmlDeviceGetUtilizationRates(h, ctypes.byref(u)) == 0 and lib.nvmlDeviceGetMemoryInfo(h, ctypes.byref(m)) == 0:
            f.write(f"{t:.3f},{u.gpu},{m.used >> 20}\n")
        time.sleep(max(0.0, period - (time.time() - t)))
