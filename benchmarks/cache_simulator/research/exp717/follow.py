"""FOLLOW: a realizable single-resident-set arbiter between LCNU and S3-FIFO.

The sealed CostFit (exp667, sha 3121d056) runs LCNU and S3-FIFO side by side at
full capacity and credits each access to whichever inner is "chosen". That is an
optimistic bound: at a switch the real expert set would have to become the other
inner's set instantly (migration not modeled, 2x residency).

FOLLOW keeps ONE real resident set R (capacity C expert slots) and uses CostFit,
unmodified, purely as metadata: both inners become ghosts (keys only, no weights).
On a real miss with R full, FOLLOW evicts a resident key that the current leader
ghost does NOT hold (set D = R minus leader). R converges lazily to the leader's
set through demand misses only -- no extra fetches, no bulk migration at a switch.

D order (deterministic): FIFO of "became out-of-leader", with a real hit moving the
key to the end. Victim = first of D; if D is empty (provably impossible when the
leader admits every miss) fall back to the LRU key of R and count it.
"""
from collections import OrderedDict

from benchmarks.cache_simulator.research.policies_costfit import CostFitPolicy


class FollowPolicy:
    def __init__(self, capacity, num_layers, prior):
        self.capacity = capacity
        self.cf = CostFitPolicy(capacity, num_layers=num_layers, prior=prior)
        self.R = OrderedDict()   # real resident set, LRU order
        self.D = OrderedDict()   # R \ leader
        self.hits = self.misses = self.fallbacks = 0
        self.d_mass = 0          # sum of |D| over accesses (lag diagnostic)
        for name, pol in self.cf._inners.items():
            pol._evict_callback = self._make_cb(name)

    def _make_cb(self, name):
        def cb(key):
            if name == self.cf.choice and key in self.R:
                self.D[key] = None
                self.D.move_to_end(key)
        return cb

    def on_access(self, key):
        before = self.cf.choice
        self.cf.on_access(key)              # ghosts + sealed control law
        L = self.cf._inners[self.cf.choice].resident
        R, D = self.R, self.D
        if self.cf.choice != before:        # switch: recompute D from scratch
            self.D = D = OrderedDict((r, None) for r in R if r not in L)
        if key in R:
            self.hits += 1
            R.move_to_end(key)
            hit = True
        else:
            self.misses += 1
            if len(R) >= self.capacity:
                if D:
                    v = next(iter(D))
                    del D[v]
                else:
                    v = next(iter(R))
                    self.fallbacks += 1
                del R[v]
            R[key] = None
            hit = False
        if key in L:
            D.pop(key, None)
        else:
            D[key] = None
            D.move_to_end(key)
        self.d_mass += len(D)
        return hit

    def check(self):
        L = self.cf._inners[self.cf.choice].resident
        assert len(self.R) <= self.capacity
        assert set(self.D) == {r for r in self.R if r not in L}, "D invariant"
