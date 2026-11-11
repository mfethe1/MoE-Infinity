#!/usr/bin/env python3
"""patch776.py — routed-set instrumentation on top of the exp773 async-dbuf patch.

Usage: python3 patch776.py <repo>/moe_infinity/memory/expert_prefetcher.py
Edits IN PLACE (run on a fresh `cp -a` copy of src753). Fails loudly if the
anchor block is not found EXACTLY once, or if the result does not parse.

Async-dbuf logic is byte-identical to patch775/773. Under EXP776_LOG_OUT the
DB path additionally logs, per speculative_prefetch call:
  {"t": n, "ts": ..., "topk": [k experts], "routed": [actually-routed set]}
- "topk":  the fresh mean-logits topk(k) list (the heuristic's pick)
- "routed": unique argmax over per-token logits = experts tokens ACTUALLY
  route to this step (ground truth for need)
NOTE: these two .cpu() calls sync — logging path only, never in the shipped
branch (EXP776_LOG_OUT unset). This run's WALL is therefore not comparable
to exp774 references; the metric is set overlap, not wall.
Marker: 'exp776 routedlog'.
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

            # exp776 routedlog (async-dbuf logic identical to exp773/775):
            # under EXP776_LOG_OUT, log per call the heuristic's topk list
            # and the set of experts tokens actually route to (argmax of
            # per-token logits). Logging syncs; the shipped path does not.
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
                _lo = os.environ.get("EXP776_LOG_OUT")
                if _lo:
                    import json as _json, time as _time
                    _t = getattr(self, "_hl_t", 0)
                    _rk = torch.topk(logits, n).indices.cpu().tolist()
                    _rt = torch.unique(
                        router_logits.float().view(-1, self.num_experts).argmax(-1)
                    ).cpu().tolist()
                    with open(_lo, "a") as _f:
                        _f.write(
                            _json.dumps(
                                {"t": _t, "ts": _time.time(), "topk": _rk, "routed": _rt}
                            )
                            + "\\n"
                        )
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
    print(f"patched {path}: routedlog x{out.count('exp776 routedlog')}, sha16={h}")

if __name__ == "__main__":
    main()
