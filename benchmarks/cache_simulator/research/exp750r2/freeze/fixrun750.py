#!/usr/bin/env python3
"""exp750: run engine_arm750.py against a PATCHED tree selected by MOEI_FIX_TREE (~/moei-fix749 or ~/moei-fix740).
Same mechanism as exp740/exp748 fixrun.py (drop the venv's editable MetaPathFinder, put the tree first, record which
moe_infinity actually loaded); the only change is that the tree comes from the environment instead of a constant."""
import json, os, runpy, sys
FIX = os.path.expanduser(os.environ["MOEI_FIX_TREE"]).rstrip("/")
assert FIX.endswith("/moei-fix749") or FIX.endswith("/moei-fix740"), FIX
sys.meta_path[:] = [f for f in sys.meta_path if "editable" not in getattr(type(f), "__module__", "") and
                    "editable" not in repr(f)]
sys.path.insert(0, FIX)
import moe_infinity, moe_infinity._store as _st  # noqa: E402
prov = {"moe_infinity": moe_infinity.__file__, "store_so": _st.__file__}
assert prov["moe_infinity"].startswith(FIX + "/") and prov["store_so"].startswith(FIX + "/"), prov
out = sys.argv[sys.argv.index("--out") + 1]
json.dump(prov, open(out + ".prov.json", "w"))
print("FIXRUN provenance", prov, flush=True)
sys.argv = [os.path.abspath("engine_arm750.py")] + sys.argv[1:]
runpy.run_path("engine_arm750.py", run_name="__main__")
