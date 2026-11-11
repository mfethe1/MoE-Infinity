#!/usr/bin/env python3
"""patch773.py — insert the exp773 async-dbuf block into expert_prefetcher.py.

Usage: python3 patch773.py <repo>/moe_infinity/memory/expert_prefetcher.py
Edits IN PLACE (run on a fresh `cp -a` copy of src753). Fails loudly if the
anchor block is not found EXACTLY once, or if the result does not parse.
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

            # exp773 async-dbuf: double-buffered GPU->CPU indices. Consume the
            # copy issued by the PREVIOUS speculative_prefetch call (its event
            # has had a full expert-layer of GPU time to drain), and issue this
            # call's topk indices back asynchronously into the other pinned
            # buffer. Removes the blocking .indices.cpu() from the critical
            # path; the prediction consumed is one call staler (exp772 showed
            # k=4-stale predictions cost ~nothing in wall time).
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
    print(f"patched {path}: marker x{out.count('exp773 async-dbuf')}, sha16={h}")

if __name__ == "__main__":
    main()
