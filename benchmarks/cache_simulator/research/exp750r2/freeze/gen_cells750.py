"""Generate cells750.json: 3 blocks x arms R1/S1/S0/P2/K2/C2/H2, order within each block =
random.Random(750).shuffle applied per block in block order (one Random instance, seeded once).
build: U = unpatched engine, F = fix749 tree (~/moei-fix749), P = fix740 tree (~/moei-fix740), H = HF.
clb: "1" = run the cell with CUDA_LAUNCH_BLOCKING=1, "" = run with CUDA_LAUNCH_BLOCKING unset."""
import json, random

ARMS = {"R1": ("U", "1", 0.2, "lcnu", ""), "S1": ("F", "1", 0.2, "lcnu", ""),
        "S0": ("F", "0", 0.2, "lcnu", ""), "P2": ("F", "0,1", 0.2, "lcnu", ""),
        "K2": ("P", "0,1", 0.2, "lcnu", "1"), "C2": ("P", "0,1", 0.2, "lcnu", ""),
        "H2": ("H", "0,1", None, "hf", "")}
rng = random.Random(750)
cells = []
for block in (1, 2, 3):
    order = ["R1", "S1", "S0", "P2", "K2", "C2", "H2"]
    rng.shuffle(order)
    for arm in order:
        build, gpus, ratio, policy, clb = ARMS[arm]
        cells.append({"build": build, "gpus": gpus, "ratio": ratio, "policy": policy,
                      "block": block, "arm": arm, "id": f"b{block}_{arm}", "clb": clb})
assert len(cells) == 21
json.dump(cells, open("cells750.json", "w"), indent=1)
print([c["id"] for c in cells])
