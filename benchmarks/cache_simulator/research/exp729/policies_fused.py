"""exp729 candidate shared-state CostFit3 variants (frozen with the PREREG; sealed tree untouched).

All three keep the SEALED CostFit3 arbiter and subclass the SEALED inner policies.

* FloorCostFit3  (``floor``): dict-like Python views over PRIVATE plain dicts (no sharing at all). Measures
  the pure cost of routing every per-key dict op through a Python-level ``__getitem__``/``__setitem__``.
* LeanCostFit3   (``lean``): one shared Key -> __slots__ record table like exp675/exp723's sealed design, but
  views drop the per-record ``live`` counter and the setitem probe (in CostFit families every accessed key
  gets LCNU slots that are never deleted, so a record can never become empty -> ``live`` is dead weight).
* FusedCostFit3  (``fused``): ONE shared Key -> list record table for all 10 per-key fields of the 4 leaf
  inners (2 LCNU x [last, ema, count, first] + 2 S3-FIFO x [freq]); the leaf hot methods that touch per-key
  state (LCNU ``_record_access``/``_probs``, S3-FIFO ``_on_hit``/``_evict_main``/``_evict_small``/``_on_miss``)
  are re-expressed over the record with the SAME statement order and the SAME float expressions. Absent
  state = ``None`` in the slot. Parity is NOT by construction here; it is verified (hit rate == exp718
  PASS-1 for every timed replay + terminal full-state equality vs sealed costfit3).
"""

import math
import sys

from benchmarks.cache_simulator.policies import LayerCycleNextUsePolicy, S3FIFOPolicy
from benchmarks.cache_simulator.research.policies_costfit3 import CostFit3Policy
from benchmarks.cache_simulator.research.policies_rothead import RotHeadPolicy


# ----------------------------------------------------------------------------- floor: private-dict views
class DictView:
    __slots__ = ("_d",)

    def __init__(self):
        self._d = {}

    def __getitem__(self, key):
        return self._d[key]

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __contains__(self, key):
        return key in self._d

    def __setitem__(self, key, value):
        self._d[key] = value

    def __delitem__(self, key):
        del self._d[key]


class _FloorLCNU(LayerCycleNextUsePolicy):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._last, self._ema, self._count, self._first = DictView(), DictView(), DictView(), DictView()


class _FloorS3(S3FIFOPolicy):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.freq = DictView()


class _FloorRot(RotHeadPolicy):
    def __init__(self, capacity, num_layers=1, prior=0.05):
        super().__init__(capacity, num_layers=num_layers, prior=prior)
        self.lcnu = _FloorLCNU(capacity, num_layers=num_layers, prior=prior)
        self.s3fifo = _FloorS3(capacity)


class FloorCostFit3(CostFit3Policy):
    def __init__(self, capacity, num_layers=1, prior=1.0 / 16):
        super().__init__(capacity, num_layers=num_layers, prior=prior)
        self._inners = {"lcnu": _FloorLCNU(capacity, num_layers=num_layers, prior=prior),
                        "s3fifo": _FloorS3(capacity),
                        "rothead": _FloorRot(capacity, num_layers=num_layers, prior=prior)}


# ----------------------------------------------------------------------------- lean: shared slot records
class LeanTable:
    def __init__(self):
        self.table = {}
        self.names = []
        self.cls = None

    def alloc(self, label):
        if self.cls is not None:
            raise RuntimeError("alloc after records exist")
        n = f"s{len(self.names)}"
        self.names.append((n, label))
        return n

    def new(self):
        if self.cls is None:
            self.cls = type("LeanRecord", (), {"__slots__": tuple(n for n, _ in self.names)})
        return self.cls()


class LeanView:
    __slots__ = ("_tab", "_new", "_name")

    def __init__(self, t, label):
        self._tab = t.table
        self._new = t.new
        self._name = t.alloc(label)

    def __getitem__(self, key):
        try:
            return getattr(self._tab[key], self._name)
        except AttributeError:
            raise KeyError(key) from None

    def get(self, key, default=None):
        rec = self._tab.get(key)
        if rec is None:
            return default
        return getattr(rec, self._name, default)

    def __contains__(self, key):
        rec = self._tab.get(key)
        return rec is not None and hasattr(rec, self._name)

    def __setitem__(self, key, value):
        rec = self._tab.get(key)
        if rec is None:
            rec = self._tab[key] = self._new()
        setattr(rec, self._name, value)

    def __delitem__(self, key):
        try:
            delattr(self._tab[key], self._name)
        except AttributeError:
            raise KeyError(key) from None


class _LeanLCNU(LayerCycleNextUsePolicy):
    def __init__(self, *a, table, role, **kw):
        super().__init__(*a, **kw)
        self.lean_table = table
        self._last, self._ema, self._count, self._first = (LeanView(table, f"{role}.{f}")
                                                           for f in ("last", "ema", "count", "first"))


class _LeanS3(S3FIFOPolicy):
    def __init__(self, *a, table, role, **kw):
        super().__init__(*a, **kw)
        self.lean_table = table
        self.freq = LeanView(table, f"{role}.freq")


class _LeanRot(RotHeadPolicy):
    def __init__(self, capacity, num_layers=1, prior=0.05, table=None, role="rothead"):
        super().__init__(capacity, num_layers=num_layers, prior=prior)
        self.lcnu = _LeanLCNU(capacity, num_layers=num_layers, prior=prior, table=table, role=f"{role}.lcnu")
        self.s3fifo = _LeanS3(capacity, table=table, role=f"{role}.s3fifo")


class LeanCostFit3(CostFit3Policy):
    def __init__(self, capacity, num_layers=1, prior=1.0 / 16):
        super().__init__(capacity, num_layers=num_layers, prior=prior)
        t = self.lean_table = LeanTable()
        self._inners = {"lcnu": _LeanLCNU(capacity, num_layers=num_layers, prior=prior, table=t, role="lcnu"),
                        "s3fifo": _LeanS3(capacity, table=t, role="s3fifo"),
                        "rothead": _LeanRot(capacity, num_layers=num_layers, prior=prior, table=t, role="rothead")}


# ----------------------------------------------------------------------------- fused: one list record per key
NSLOT = 10  # lcnu[0:4] s3fifo[4] rothead.lcnu[5:9] rothead.s3fifo[9]


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


class _FusedRot(RotHeadPolicy):
    def __init__(self, capacity, num_layers=1, prior=0.05, tab=None):
        super().__init__(capacity, num_layers=num_layers, prior=prior)
        self.lcnu = _FusedLCNU(capacity, num_layers=num_layers, prior=prior, tab=tab, off=5)
        self.s3fifo = _FusedS3(capacity, tab=tab, idx=9)


class FusedCostFit3(CostFit3Policy):
    def __init__(self, capacity, num_layers=1, prior=1.0 / 16):
        super().__init__(capacity, num_layers=num_layers, prior=prior)
        t = self.fused_table = {}
        self._inners = {"lcnu": _FusedLCNU(capacity, num_layers=num_layers, prior=prior, tab=t, off=0),
                        "s3fifo": _FusedS3(capacity, tab=t, idx=4),
                        "rothead": _FusedRot(capacity, num_layers=num_layers, prior=prior, tab=t)}


ARMS = {"floor": FloorCostFit3, "lean": LeanCostFit3, "fused": FusedCostFit3}

# ----------------------------------------------------------------------------- census + full-state parity
_LEAVES = (("lcnu", None), ("s3fifo", None), ("rothead", "lcnu"), ("rothead", "s3fifo"))
_LF = ("_last", "_ema", "_count", "_first")


def _leaf(pol, a, b):
    x = pol._inners[a]
    return getattr(x, b) if b else x


def census(pol):
    """getsizeof of per-key containers (values excluded, == exp675a/CEN methodology), deterministic walk."""
    tables = records = slots = size = 0
    if isinstance(pol, FusedCostFit3):
        t = pol.fused_table
        tables, size = 1, sys.getsizeof(t)
        for k in sorted(t):
            r = t[k]
            records += 1
            slots += sum(v is not None for v in r)
            size += sys.getsizeof(r)
    elif isinstance(pol, LeanCostFit3):
        t = pol.lean_table.table
        names = [n for n, _ in pol.lean_table.names]
        tables, size = 1, sys.getsizeof(t)
        for k in sorted(t):
            r = t[k]
            records += 1
            slots += sum(hasattr(r, n) for n in names)
            size += sys.getsizeof(r)
    else:
        for a, b in _LEAVES:
            leaf = _leaf(pol, a, b)
            for f in (_LF if "lcnu" in (b or a) else ("freq",)):
                d = getattr(leaf, f)
                d = d._d if isinstance(d, DictView) else d
                tables += 1
                records += len(d)
                slots += len(d)
                size += sys.getsizeof(d)
    return {"tables": tables, "records": records, "slots": slots, "struct_bytes": size}


def full_state(pol):
    """Canonical terminal state: arbiter + every leaf's order structures + every per-key field."""
    st = {"choice": pol.choice, "switches": pol.switches, "choice_switches": dict(pol.choice_switches),
          "mass": {k: list(v) for k, v in pol._mass.items()}, "sw_mass": pol._sw_mass,
          "credited": list(pol._credited), "leaves": []}
    for a, b in _LEAVES:
        leaf = _leaf(pol, a, b)
        L = {"resident": list(leaf.resident), "hits": leaf.hits, "misses": leaf.misses}
        if "lcnu" in (b or a):
            L["visits"] = dict(leaf._visits)
            L["by_layer"] = {k: sorted(v) for k, v in leaf._by_layer.items()}
            if isinstance(leaf, _FusedLCNU):
                o, t = leaf._o, leaf._tab
                L["fields"] = {k: tuple(t[k][o:o + 4]) for k in sorted(t) if t[k][o] is not None}
            else:
                g = [getattr(leaf, f) for f in _LF]
                ks = g[0]._d if isinstance(g[0], DictView) else (
                    {k for k in leaf.lean_table.table if hasattr(leaf.lean_table.table[k], g[0]._name)}
                    if isinstance(g[0], LeanView) else g[0])
                L["fields"] = {k: tuple(x[k] for x in g) for k in sorted(ks)}
        else:
            L["small"], L["main"], L["ghost"] = list(leaf.small), list(leaf.main), list(leaf.ghost)
            if isinstance(leaf, _FusedS3):
                t, i = leaf._tab, leaf._i
                L["freq"] = {k: t[k][i] for k in sorted(t) if t[k][i] is not None}
            else:
                f = leaf.freq
                if isinstance(f, DictView):
                    L["freq"] = dict(sorted(f._d.items()))
                elif isinstance(f, LeanView):
                    tb = leaf.lean_table.table
                    L["freq"] = {k: getattr(tb[k], f._name) for k in sorted(tb) if hasattr(tb[k], f._name)}
                else:
                    L["freq"] = dict(sorted(f.items()))
        st["leaves"].append(L)
    return st
