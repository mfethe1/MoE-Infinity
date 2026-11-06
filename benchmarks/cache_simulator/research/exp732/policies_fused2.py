"""exp732 candidate: FusedCostFit — exp729's fused per-key record ported to the N=2 CostFit head.

The N=2 CostFit head (lcnu vs s3fifo, sealed policies_costfit.py) at its sealed class parameters is the head the
joint 2-trace BO line settled on: exp714 (NO-TRAIN-HEADROOM) found center (MARGIN 0.005, GAMMA 0.0025,
HALF_LIFE 32768) at the bar-constrained mean optimum after exp669's BO winner broke safety (exp674). No parameter
is overridden here.

FusedCostFit keeps the SEALED CostFit arbiter and subclasses the SEALED inner policies. ONE shared Key -> list record
table holds all 5 per-key fields (LCNU [last, ema, count, first] at rec[0:4], S3-FIFO [freq] at rec[4]). The leaf
methods touching per-key state are exp729's sealed fused methods (policies_fused.py, sha-pinned) with NSLOT 10 -> 5
and the offsets re-based; statement order and float expressions are unchanged from the sealed leaves. Absent state =
``None`` in the slot. Parity is NOT by construction: it is verified (every timed replay hit rate == exp718 PASS-1
costfit, and round-0 terminal full-state equality vs sealed costfit).
"""

import math
import sys

from benchmarks.cache_simulator.policies import LayerCycleNextUsePolicy, S3FIFOPolicy
from benchmarks.cache_simulator.research.policies_costfit import CostFitPolicy

NSLOT = 5  # lcnu[0:4] s3fifo[4]


class _FusedLCNU(LayerCycleNextUsePolicy):
    """LCNU with [last, ema, count, first] at rec[o:o+4]; statement order + float expressions == sealed."""

    def __init__(self, *a, tab, off, **kw):
        super().__init__(*a, **kw)
        self._tab = tab
        self._o = off
        del self._last, self._ema, self._count, self._first  # no hidden fallback to the private dicts

    def _probs(self, keys, visits):
        beta, prior, log_keep = self.beta, self.prior, self._log_keep
        tab, o = self._tab, self._o
        exp = math.exp
        out = []
        for key in keys:
            r = tab[key]
            recent = r[o + 1] * exp(log_keep * (visits - r[o]))
            freq = (r[o + 2] + 4.0 * prior) / (visits - r[o + 3] + 4.0)
            p = beta * recent + (1.0 - beta) * freq
            out.append(p if p > 1e-12 else 1e-12)
        return out

    def _record_access(self, key):
        layer = key[0]
        if layer > self._max_layer:
            self._max_layer = layer
            if self.num_layers is None:
                self._cand.clear()
        if layer != self._cur:
            self._cur = layer
            self._visits[layer] += 1
            self._stale.add(layer)
            self._used_now = set()
        visit = self._visits[layer]
        r = self._tab.get(key)
        if r is None:
            r = self._tab[key] = [None] * NSLOT
        o = self._o
        last = r[o]
        if last is None:
            r[o + 1] = (1.0 - self.alpha) * self.prior + self.alpha
            r[o + 2] = 1
            r[o + 3] = visit - 1
        elif visit > last:
            gap = visit - last
            r[o + 1] = r[o + 1] * math.exp(self._log_keep * gap) + self.alpha
            r[o + 2] += 1
        r[o] = visit
        self._used_now.add(key)


class _FusedS3(S3FIFOPolicy):
    """S3-FIFO with freq at rec[i]; ``del freq[k]`` == set None. Statement order == sealed."""

    def __init__(self, *a, tab, idx, **kw):
        super().__init__(*a, **kw)
        self._tab = tab
        self._i = idx
        del self.freq

    def _on_hit(self, key):
        r, i = self._tab[key], self._i
        if r[i] < 3:
            r[i] += 1

    def _evict_main(self):
        main, tab, i = self.main, self._tab, self._i
        while main:
            old, _ = main.popitem(last=False)
            r = tab[old]
            if r[i] > 0:
                r[i] -= 1
                main[old] = None
            else:
                r[i] = None
                self._evict(old)
                return

    def _evict_small(self):
        small, tab, i = self.small, self._tab, self._i
        while small:
            old, _ = small.popitem(last=False)
            r = tab[old]
            if r[i] > 1:
                r[i] = 0
                self.main[old] = None
                if len(self.main) > self.m_cap:
                    self._evict_main()
            else:
                r[i] = None
                self._evict(old)
                self.ghost[old] = None
                if len(self.ghost) > self.m_cap:
                    self.ghost.popitem(last=False)
                return

    def _on_miss(self, key):
        while len(self.resident) >= self.capacity:
            if len(self.small) >= self.s_cap or not self.main:
                self._evict_small()
            else:
                self._evict_main()
        r = self._tab.get(key)
        if r is None:
            r = self._tab[key] = [None] * NSLOT
        r[self._i] = 0
        if key in self.ghost:
            del self.ghost[key]
            self.main[key] = None
        else:
            self.small[key] = None
        self._insert(key)


class FusedCostFit(CostFitPolicy):
    def __init__(self, capacity, num_layers=1, prior=1.0 / 16):
        super().__init__(capacity, num_layers=num_layers, prior=prior)
        t = self.fused_table = {}
        self._inners = {"lcnu": _FusedLCNU(capacity, num_layers=num_layers, prior=prior, tab=t, off=0),
                        "s3fifo": _FusedS3(capacity, tab=t, idx=4)}


ARMS = {"fused2": FusedCostFit}

# ----------------------------------------------------------------------------- census + full-state parity
_LF = ("_last", "_ema", "_count", "_first")

# C-level byte model (descriptive, frozen formula): open addressing, load factor 0.75, u32 packed (layer, expert) key.
C_LOAD = 0.75
C_SOA_SLOT = {"last": 8, "ema": 16, "count": 8, "first": 8, "freq": 8}   # per-field maps {u32 key, value(+pad)}
C_AOS_REC = 32  # {u32 key; u32 last; u32 count; u32 first; f64 ema; u8 freq; pad} -> 4+4+4+4+8+1 = 25 -> 32 aligned


def census(pol):
    """getsizeof of per-key containers (values excluded, == exp675a/CEN methodology), deterministic walk.

    Also returns per-field occupancy for the descriptive C-level byte model."""
    tables = records = slots = size = 0
    occ_lcnu = occ_s3 = 0
    if isinstance(pol, FusedCostFit):
        t = pol.fused_table
        tables, size = 1, sys.getsizeof(t)
        for k in sorted(t):
            r = t[k]
            records += 1
            slots += sum(v is not None for v in r)
            occ_lcnu += r[0] is not None
            occ_s3 += r[4] is not None
            size += sys.getsizeof(r)
    else:
        for name in ("lcnu", "s3fifo"):
            leaf = pol._inners[name]
            for f in (_LF if name == "lcnu" else ("freq",)):
                d = getattr(leaf, f)
                tables += 1
                records += len(d)
                slots += len(d)
                size += sys.getsizeof(d)
            if name == "lcnu":
                occ_lcnu = len(leaf._last)
            else:
                occ_s3 = len(leaf.freq)
    return {"tables": tables, "records": records, "slots": slots, "struct_bytes": size,
            "occ_lcnu": occ_lcnu, "occ_s3": occ_s3}


def c_model(fused_census):
    """Descriptive C-level bytes from the fused census: SoA (5 per-field maps) vs AoS (one map of 32 B records)."""
    n_keys, n_l, n_s = fused_census["records"], fused_census["occ_lcnu"], fused_census["occ_s3"]
    soa = (n_l * (C_SOA_SLOT["last"] + C_SOA_SLOT["ema"] + C_SOA_SLOT["count"] + C_SOA_SLOT["first"])
           + n_s * C_SOA_SLOT["freq"]) / C_LOAD
    aos = n_keys * C_AOS_REC / C_LOAD
    return {"keys": n_keys, "soa_bytes": soa, "aos_bytes": aos, "aos_over_soa": aos / soa if soa else None}


def full_state(pol):
    """Canonical terminal state: arbiter + both leaves' order structures + every per-key field."""
    st = {"choice": pol.choice, "switches": pol.switches, "since": pol._since,
          "mass": {k: list(v) for k, v in pol._mass.items()}, "sw_mass": pol._sw_mass,
          "credited": list(pol._credited), "leaves": []}
    for name in ("lcnu", "s3fifo"):
        leaf = pol._inners[name]
        L = {"resident": list(leaf.resident), "hits": leaf.hits, "misses": leaf.misses}
        if name == "lcnu":
            L["visits"] = dict(leaf._visits)
            L["by_layer"] = {k: sorted(v) for k, v in leaf._by_layer.items()}
            if isinstance(leaf, _FusedLCNU):
                o, t = leaf._o, leaf._tab
                L["fields"] = {k: tuple(t[k][o:o + 4]) for k in sorted(t) if t[k][o] is not None}
            else:
                g = [getattr(leaf, f) for f in _LF]
                L["fields"] = {k: tuple(x[k] for x in g) for k in sorted(g[0])}
        else:
            L["small"], L["main"], L["ghost"] = list(leaf.small), list(leaf.main), list(leaf.ghost)
            if isinstance(leaf, _FusedS3):
                t, i = leaf._tab, leaf._i
                L["freq"] = {k: t[k][i] for k in sorted(t) if t[k][i] is not None}
            else:
                L["freq"] = dict(sorted(leaf.freq.items()))
        st["leaves"].append(L)
    return st
