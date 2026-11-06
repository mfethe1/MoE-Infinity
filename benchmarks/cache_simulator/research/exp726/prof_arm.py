#!/usr/bin/env python3
"""exp726 descriptive profile: engine lcnu @ratio, torch.profiler over one 16-token decode (after warmup)."""
import sys, json, torch
from transformers import AutoTokenizer
from torch.profiler import profile, ProfilerActivity
from moe_infinity import MoE
model_p, off, ratio, outp = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
tok = AutoTokenizer.from_pretrained(model_p)
m = MoE(model_p, {"offload_path": off, "device_memory_ratio": ratio, "expert_eviction_policy": "lcnu"})
p = json.load(open("prompts.json"))[0]
ids = tok.apply_chat_template([{"role": "user", "content": p}], add_generation_prompt=True, return_tensors="pt",
                              return_dict=True)["input_ids"].to("cuda:0")
with torch.no_grad():
    m.generate(ids, max_new_tokens=16, min_new_tokens=16, do_sample=False, pad_token_id=tok.eos_token_id)
    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as pr:
        m.generate(ids, max_new_tokens=16, min_new_tokens=16, do_sample=False, pad_token_id=tok.eos_token_id)
        torch.cuda.synchronize()
ka = pr.key_averages()
with open(outp, "w") as f:
    f.write(ka.table(sort_by="self_cpu_time_total", row_limit=25)); f.write("\n\n")
    f.write(ka.table(sort_by="self_cuda_time_total", row_limit=15))
    tot_cpu = sum(e.self_cpu_time_total for e in ka); tot_cuda = sum(e.self_device_time_total for e in ka)
    f.write(f"\nTOTAL self_cpu_us={tot_cpu:.0f} self_cuda_us={tot_cuda:.0f}\n")
print("PROF-DONE", outp)
