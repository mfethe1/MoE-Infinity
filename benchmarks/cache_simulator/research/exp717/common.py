"""exp715 shared helpers: stream loading (identical to sealed exp704), C++ driver calls."""
import subprocess, sys, time
from pathlib import Path

import torch

HOME = Path.home()
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D / "ref"))  # upstream-main simulator (pinned, see UPSTREAM_SHA)
from benchmarks.cache_simulator.policies import build_policy, simulate  # noqa: E402

POLICIES = ["lru", "lfu", "lfu_k", "lhu", "lru_k", "arc", "2q", "lirs",
            "s3fifo", "sieve", "w_tinylfu", "layer_lru", "lcnu"]
ALPHA, BETA = 0.3, 0.5  # engine / simulator LCNU defaults

TRACES = {  # copied verbatim from sealed exp704 run_capacitymap.py
    "granite": {"pt": HOME / "warp-work/exp650-moei-granite3b-trace-pr/stream_granite3b.pt",
                "nl": 32, "prior": 0.2, "N": 638208, "distinct": 1262,
                "caps": [128, 192, 256, 384, 512, 640, 768, 896, 1024], "det": 256},
    "hi": {"pt": HOME / "warp-work/exp656-moei-within/stream_qwen30b_hi.pt",
           "nl": 48, "prior": 8 / 128, "N": 786432, "distinct": 5097,
           "caps": [768, 896, 1024, 1152, 1280, 1408, 1536, 1792, 2048], "det": 1024},
    "lo": {"pt": HOME / "warp-work/exp656-moei-within/stream_qwen30b_lo.pt",
           "nl": 48, "prior": 8 / 128, "N": 638208, "distinct": 5842,
           "caps": [768, 896, 1024, 1152, 1280, 1408, 1536, 1792, 2048], "det": 1024},
}


def load_keys(tag):
    cfg = TRACES[tag]
    s = torch.load(str(cfg["pt"]), map_location="cpu", weights_only=False)
    keys = []
    for r in s["records"]:
        t = r["topk_ids_of_layer"]
        if r["forward_mode"] == 1:
            continue  # prefill pass: excluded exactly as exp704 (decode-only stream)
        for l in range(t.shape[0]):
            for e in t[l, 0].tolist():
                keys.append((l, e))
    assert len(keys) == cfg["N"] and len(set(keys)) == cfg["distinct"], (tag, len(keys))
    return keys


def trace_text(keys):
    return "\n".join([str(len(keys))] + [f"{l} {e}" for l, e in keys])


def cpp_hits(trace_txt, queries, driver=D / "driver"):
    lines = [trace_txt, str(len(queries))]
    lines += [f"{n} {c} {nl} {a!r} {b!r} {p!r}" for n, c, nl, a, b, p in queries]
    t0 = time.perf_counter()
    r = subprocess.run([str(driver)], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, check=True)
    return [int(x) for x in r.stdout.split()], time.perf_counter() - t0


def py_hits(name, cap, keys, nl, prior):
    kw = {}
    if name == "layer_lru":
        kw = {"num_layers": nl}
    elif name == "lcnu":
        kw = {"num_layers": nl, "alpha": ALPHA, "beta": BETA, "prior": prior}
    h, m, _ = simulate(build_policy(name, cap, **kw), keys)
    return h
