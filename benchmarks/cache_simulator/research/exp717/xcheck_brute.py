"""Independent brute-force re-implementation of FOLLOW's real-set bookkeeping (no incremental D).

Each step recomputes out = {r in R : r not in leader} from scratch and orders victims by explicit
timestamps; compares hit count and victim stream against follow.FollowPolicy on trace prefixes.
"""
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D))
from common import TRACES, load_keys  # noqa: E402
from follow import FollowPolicy  # noqa: E402
from benchmarks.cache_simulator.research.policies_costfit import CostFitPolicy  # noqa: E402


def brute(keys, cap, nl, prior):
    cf = CostFitPolicy(cap, num_layers=nl, prior=prior)
    ev = []  # eviction order within a step: ONLY used to break same-step timestamp ties
    for nm, pol in cf._inners.items():
        pol._evict_callback = (lambda key, nm=nm: ev.append((nm, key)))
    R, touch, stamp, prev_out = set(), {}, {}, set()
    hits = 0
    for t, k in enumerate(keys):
        before = cf.choice
        ev.clear()
        cf.on_access(k)
        L = cf._inners[cf.choice].resident
        out_now = {r for r in R if r not in L}
        if cf.choice != before:
            for r in out_now:
                stamp[r] = (touch[r], 0, 0)
        else:
            order = {key: i for i, (nm, key) in enumerate(ev) if nm == before}
            for r in out_now - prev_out:
                stamp[r] = (t, 0, order[r])
        if k in R:
            hits += 1
        else:
            if len(R) >= cap:
                v = min(out_now, key=lambda r: stamp[r]) if out_now else min(R, key=lambda r: touch[r])
                R.discard(v); out_now.discard(v)
            R.add(k)
        touch[k] = t
        if k in L:
            out_now.discard(k)
        else:
            out_now.add(k); stamp[k] = (t, 1, 0)
        prev_out = out_now
    return hits, cf.switches


for tag, cap, n in [(a, int(b), int(c)) for a, b, c in (x.split(":") for x in sys.argv[1:])]:
    keys = load_keys(tag)[:n]
    cfg = TRACES[tag]
    f = FollowPolicy(cap, cfg["nl"], cfg["prior"])
    for k in keys:
        f.on_access(k)
    bh, bs = brute(keys, cap, cfg["nl"], cfg["prior"])
    print(tag, cap, n, "follow", f.hits, "brute", bh, "switches", f.cf.switches, bs, "MATCH" if (f.hits, f.cf.switches) == (bh, bs) else "MISMATCH")
