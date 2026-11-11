#!/usr/bin/env python3
"""patch775.py — hit-rate-instrumented superset of the exp773 async-dbuf patch.

Usage: python3 patch775.py <repo>/moe_infinity/memory/expert_prefetcher.py
Edits IN PLACE (run on a fresh `cp -a` copy of src753). Fails loudly if the
anchor block is not found EXACTLY once, or if the result does not parse.

Differences from patch773.py (the async-dbuf intervention is byte-identical
in logic): both paths optionally log one JSON line per speculative_prefetch
call when EXP775_LOG_OUT is set —
  DB path (EXP773_DB=1):  {"t": n, "ts": ..., "consumed": [...]}  — the list
      consumed this call (= the previous call's issued topk; already on the
      CPU, so logging adds NO synchronization)
  blocking path:          {"t": n, "ts": ..., "issued": [...]}    — the list
      computed this call (the .tolist() result; already on the CPU)
Marker: 'exp775 hitlog' (plus the retained 'exp773 async-dbuf' comment).
"""
import ast, hashlib, sys

ORIG = '''        if hasattr(router_logits, "topk"):
            import torch

            topk_indices: List[int] = (
                torch.topk(
                    router_logits.float().view(-1, self.num_experts).mean(0),
                    num_experts_to_prefetch,
                )
                .indices.cpu()
                .tolist()
            )
'''

NEW = '''        if hasattr(router_logits, "topk"):
            import torch
            import os

            # exp775 hitlog (superset of exp773 async-dbuf): identical
            # double-buffered GPU->CPU indices logic, plus optional
            # per-call hit-rate logging (EXP775_LOG_OUT). The DB path logs
            # the CONSUMED (previous call's) list -- already on the CPU, so
            # logging adds no synchronization. The blocking path logs the
            # freshly computed list (also already on the CPU).
            if os.environ.get("EXP773_DB") == "1":
                if getattr(self, "_db_slot", None) is None:
                    self._db_slot = 0
                    self._db_buf = [None, None]
                    self._db_evt = [None, None]
                logits = router_logits.float().view(-1, self.num_experts).mean(0)
                n = num_experts_to_prefetch
                slot = self._db_slot
                if self._db_evt[slot] is not None:
                    self._db_evt[slot].synchronize()
                    topk_indices = self._db_buf[slot][:n].tolist()
                else:
                    topk_indices = torch.topk(logits, n).indices.cpu().tolist()
                oslot = 1 - slot
                if self._db_buf[oslot] is None:
                    self._db_buf[oslot] = torch.empty(
                        self.num_experts, dtype=torch.long, pin_memory=True
                    )
                self._db_buf[oslot].copy_(
                    torch.topk(logits, self.num_experts).indices, non_blocking=True
                )
                self._db_evt[oslot] = torch.cuda.Event()
                self._db_evt[oslot].record()
                self._db_slot = oslot
                _lo = os.environ.get("EXP775_LOG_OUT")
                if _lo:
                    import json as _json, time as _time
                    _t = getattr(self, "_hl_t", 0)
                    with open(_lo, "a") as _f:
                        _f.write(_json.dumps({"t": _t, "ts": _time.time(), "consumed": topk_indices}) + "\\n")
                    self._hl_t = _t + 1
            else:
                topk_indices: List[int] = (
                    torch.topk(
                        router_logits.float().view(-1, self.num_experts).mean(0),
                        num_experts_to_prefetch,
                    )
                    .indices.cpu()
                    .tolist()
                )
                _lo = os.environ.get("EXP775_LOG_OUT")
                if _lo:
                    import json as _json, time as _time
                    _t = getattr(self, "_hl_t", 0)
                    with open(_lo, "a") as _f:
                        _f.write(_json.dumps({"t": _t, "ts": _time.time(), "issued": topk_indices}) + "\\n")
                    self._hl_t = _t + 1
'''

def main():
    path = sys.argv[1]
    src = open(path).read()
    n = src.count(ORIG)
    assert n == 1, f"anchor count {n} != 1"
    out = src.replace(ORIG, NEW)
    ast.parse(out)
    open(path, "w").write(out)
    h = hashlib.sha256(out.encode()).hexdigest()[:16]
    print(f"patched {path}: hitlog x{out.count('exp775 hitlog')}, dbuf x{out.count('exp773 async-dbuf')}, sha16={h}")

if __name__ == "__main__":
    main()
