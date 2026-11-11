#!/usr/bin/env python3
import ast, sys
F = "/home/mfeth/exp772/src772/moe_infinity/memory/expert_prefetcher.py"
t = open(F).read()
ANCHOR = '        if hasattr(router_logits, "topk"):'
assert t.count(ANCHOR) == 1, f"anchor count {t.count(ANCHOR)}"
GUARD = '\n        # exp772 k-stride: recompute the topk prediction (and its GPU->CPU\n        # sync at the .indices.cpu() line) only every k-th call; between\n        # strides reuse the previous prediction set. EXP772_K=1 disables.\n        import os as _os772\n        try:\n            _k772 = int(_os772.environ.get("EXP772_K", "1"))\n        except ValueError:\n            _k772 = 1\n        self._step772 = getattr(self, "_step772", 0) + 1\n        if _k772 > 1 and (self._step772 % _k772) != 1 and self._last_speculative_prediction:\n            _ids772 = sorted(self._last_speculative_prediction)\n            if self._overlap_active():\n                generation, _accepted = self.plan_candidates(\n                    next_layer, _ids772\n                )\n                return\n            self.prefetch_experts_list(\n                next_layer, _ids772, priority=priority, phase=phase\n            )\n            return\n\n'
assert "exp772 k-stride" not in t
t2 = t.replace(ANCHOR, GUARD + ANCHOR)
ast.parse(t2)  # syntax gate
open(F, "w").write(t2)
print("patched; marker present:", "exp772 k-stride" in open(F).read())
