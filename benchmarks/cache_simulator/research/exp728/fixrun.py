#!/usr/bin/env python3
"""exp728: run engine_arm.py against the PATCHED tree. The venv's editable install registers a MetaPathFinder that
would shadow PYTHONPATH, so drop it, put the fix tree first, and record which moe_infinity actually loaded."""
import json, os, runpy, sys
FIX = os.path.expanduser("~/moei-fix728")
sys.meta_path[:] = [f for f in sys.meta_path if "editable" not in getattr(type(f), "__module__", "") and
                    "editable" not in repr(f)]
sys.path.insert(0, FIX)
import moe_infinity, moe_infinity._store as _st  # noqa: E402
prov = {"moe_infinity": moe_infinity.__file__, "store_so": _st.__file__}
assert prov["moe_infinity"].startswith(FIX + "/") and prov["store_so"].startswith(FIX + "/"), prov
out = sys.argv[sys.argv.index("--out") + 1]
json.dump(prov, open(out + ".prov.json", "w"))
print("FIXRUN provenance", prov, flush=True)
sys.argv = [os.path.abspath("engine_arm.py")] + sys.argv[1:]
runpy.run_path("engine_arm.py", run_name="__main__")
