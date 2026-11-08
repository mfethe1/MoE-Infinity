"""exp753 G cell: CUDA-graph capture feasibility probe (disposable subprocesses).

Question: can any part of the per-layer MoE-Infinity dispatch path be
stream-captured into a CUDA graph on this WSL2/driver/engine stack (the
precondition for a graph-based decode step)?

SUB-3 fixes applied (SUB3-out.md #1-#5):
  #1  step 4 verifies REPLAY OUTPUT: every replay's wait_hidden_states() result is
      compared (allclose) against the eager outputs; CAPTURE-OK is gated on it.
  #2  fail-fast: after any FAILED capture attempt no later sync/wait runs; the
      probe child records its result and os._exit's immediately (no stranding).
  #3  every probe runs in its own disposable subprocess (fresh CUDA context);
      a failed capture cannot poison a later probe's attribution.
  #4  cudaLaunchHostFunc: captured=True requires rc==0 AND replay callback fired;
      rc recorded in ALL paths.
  #5  exit code: 0 = all outcomes recorded cleanly (incl. genuine CAPTURE-FAIL,
      which is a scientific result); 3 = positive control FAIL (INCONCLUSIVE-ENV);
      2 = probe crash (unrecorded); 1 = missing/undecodable probe result.

Structure: this file is BOTH the driver (--out OUT.json) and the per-probe child
(--step {pc,pinned,hostfn,dispatch} --step-out FILE). The driver itself never
touches CUDA; children exit via os._exit after writing their JSON (disposable).
"""
import argparse, ctypes, json, os, platform, subprocess, sys, time, traceback

PROBES = ("pc", "pinned", "hostfn", "dispatch")


def rec(out, step, **kw):
    kw["step"] = step
    out["steps"].append(kw)
    print("PROBE", json.dumps(kw)[:400], flush=True)


def dump_exit(out, path, code=0):
    """Record everything known, then exit without draining any engine state."""
    json.dump(out, open(path, "w"), indent=1)
    os._exit(code)


# --------------------------- child: step 0 -------------------------------------
def child_pc(a):
    import torch
    out = {"step": "positive_control", "steps": []}
    dev = "cuda:0"
    try:
        x = torch.ones(4, device=dev)
        g = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g):
            y = x + 1
        g.replay()
        torch.cuda.synchronize()
        ok = bool((y == 2).all().item())
        out.update(ok=ok, values=y.tolist())
        dump_exit(out, a.step_out, 0 if ok else 3)
    except Exception as e:
        out.update(ok=False, error=repr(e), tb=traceback.format_exc()[-800:])
        dump_exit(out, a.step_out, 3)


# --------------------------- child: step 1 -------------------------------------
def child_pinned(a):
    import torch
    out = {"step": "pinned_alloc_capture", "steps": []}
    try:
        g1 = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g1):
            src = torch.randn(1, a.hidden, device="cuda:0")
            pinned = torch.empty(1, a.hidden, pin_memory=True)
            pinned.copy_(src)
        out.update(captured=True)
        dump_exit(out, a.step_out, 0)
    except Exception as e:
        # FAIL-fast (fix #2): do not sync/wait/replay anything after this.
        out.update(captured=False, error=repr(e), err_type=type(e).__name__)
        dump_exit(out, a.step_out, 0)  # recorded scientific outcome, not a crash


# --------------------------- child: step 2 -------------------------------------
def child_hostfn(a):
    import torch
    out = {"step": "hostfn_capture", "steps": []}
    cb_fired = [0]
    rc = None
    try:
        CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p)

        def _noop(_):
            cb_fired[0] += 1

        cb = CB(_noop)
        cudart = ctypes.CDLL("libcudart.so.12", mode=ctypes.RTLD_GLOBAL)
        cudart.cudaLaunchHostFunc.restype = ctypes.c_int
        cudart.cudaLaunchHostFunc.argtypes = [ctypes.c_void_p, CB, ctypes.c_void_p]
        cudart.cudaGetErrorString.restype = ctypes.c_char_p
        cudart.cudaGetErrorString.argtypes = [ctypes.c_int]
        g2 = torch.cuda.CUDAGraph()
        stream = torch.cuda.current_stream().cuda_stream
        with torch.cuda.graph(g2):
            rc = cudart.cudaLaunchHostFunc(ctypes.c_void_p(stream), cb, None)
        errstr = cudart.cudaGetErrorString(rc).decode() if rc is not None else None
        cap_fired = cb_fired[0]  # capture-phase firings (usually 0)
        out.update(launch_rc=rc, launch_err=errstr, capture_cb_fired=cap_fired)
        if rc != 0:
            # fix #4: nonzero rc is a FAIL even without an exception; do NOT
            # replay/sync afterwards (capture may be incomplete).
            out.update(captured=False, replay_cb_fired=0)
            dump_exit(out, a.step_out, 0)
        g2.instantiate()
        g2.replay()
        torch.cuda.synchronize()
        fired = cb_fired[0] - cap_fired  # replay-specific firings (fix #7)
        out.update(captured=bool(rc == 0 and fired >= 1), replay_cb_fired=fired)
        dump_exit(out, a.step_out, 0)
    except Exception as e:
        out.update(captured=False, error=repr(e), launch_rc=rc,
                   replay_cb_fired=cb_fired[0])
        dump_exit(out, a.step_out, 0)


# --------------------------- child: step 3a/3b/4 --------------------------------
def child_dispatch(a):
    import torch
    from transformers import AutoConfig, AutoTokenizer
    from moe_infinity import MoE
    out = {"step": "dispatch_capture", "steps": []}
    dev = "cuda:0"
    t0 = time.perf_counter()
    model = MoE(a.model, {"offload_path": a.offload, "device_memory_ratio": a.ratio,
                          "expert_eviction_policy": a.policy, "num_threads": a.threads,
                          "gpu_only_expert_routing": a.gpu_route == "on"})
    out["load_s"] = time.perf_counter() - t0
    acfg_t = AutoConfig.from_pretrained(a.model)
    hidden, nexp = acfg_t.hidden_size, getattr(acfg_t, "num_experts", 64)
    out["hidden"], out["num_experts"] = hidden, nexp
    tok = AutoTokenizer.from_pretrained(a.model)
    prompts = json.load(open(a.prompts))

    def _walk(obj, depth=0, seen=None):
        seen = seen if seen is not None else set()
        if obj is None or id(obj) in seen or depth > 5 or isinstance(obj, (int, float, str, bytes, torch.Tensor)):
            return
        seen.add(id(obj))
        yield obj
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict):
            for v in list(d.values()):
                yield from _walk(v, depth + 1, seen)

    def find_attr(root, method):
        for o in _walk(root):
            if callable(getattr(type(o), method, None)) or (
                    type(o).__module__.startswith("moe_infinity._") and hasattr(o, method)):
                return o

    disp = find_attr(model, "set_inputs_with_invocation")
    out["dispatcher_found"] = disp is not None
    has_dispatch = disp is not None and hasattr(disp, "dispatch_experts")
    has_wait = disp is not None and hasattr(disp, "wait_hidden_states")
    out["methods"] = {"set_inputs_with_invocation": disp is not None,
                      "dispatch_experts": has_dispatch, "wait_hidden_states": has_wait}

    # warm to steady residency with one real generation (BEFORE any capture
    # attempt — fix #2 ordering: no sync/wait runs after a failed capture).
    ids = tok.apply_chat_template([{"role": "user", "content": prompts[0]}],
                                  add_generation_prompt=True, return_tensors="pt",
                                  return_dict=True)["input_ids"].to(dev)
    with torch.no_grad():
        model.generate(ids, max_new_tokens=a.max_new, min_new_tokens=a.max_new,
                       do_sample=False, pad_token_id=tok.eos_token_id)
    torch.cuda.synchronize()
    rec(out, "warmup", ok=True)

    if disp is None or not has_dispatch:
        out.update(dispatch_capture="SKIP", note="dispatcher-methods-missing")
        dump_exit(out, a.step_out, 0)

    h = torch.randn(1, hidden, device=dev)
    mask = torch.zeros(1, nexp, dtype=torch.bool, device=dev)
    mask[0, :6] = True
    w = torch.rand(1, nexp, device=dev)
    try:  # eager warm of the layer-0 path, then drain (pre-capture only)
        iid = disp.set_inputs_with_invocation(h, mask, w)
        disp.dispatch_experts(0)
        if has_wait:
            _ = disp.wait_hidden_states()
        torch.cuda.synchronize()
        rec(out, "eager_layer0", ok=True, invocation_id=int(iid))
    except Exception as e:
        rec(out, "eager_layer0", ok=False, error=repr(e))
        out.update(dispatch_capture="FAIL:eager-warm")
        dump_exit(out, a.step_out, 0)

    # ---- step 3a: set_inputs inside capture --------------------------------
    try:
        g3 = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g3):
            disp.set_inputs_with_invocation(h, mask, w)
        rec(out, "setinputs_capture", captured=True)
    except Exception as e:
        rec(out, "setinputs_capture", captured=False, error=repr(e))
        out.update(dispatch_capture="FAIL@setinputs")
        dump_exit(out, a.step_out, 0)  # fail-fast: nothing else is waited on

    # ---- step 3b: set_inputs + dispatch_experts inside capture -------------
    try:
        g4 = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g4):
            disp.set_inputs_with_invocation(h, mask, w)
            disp.dispatch_experts(0)
        rec(out, "dispatch_capture_step", captured=True)
    except Exception as e:
        rec(out, "dispatch_capture_step", captured=False, error=repr(e))
        out.update(dispatch_capture="FAIL@dispatch")
        dump_exit(out, a.step_out, 0)  # fail-fast

    # ---- step 4: replay x32 vs eager x32, OUTPUT-VERIFIED (fix #1) ---------
    if not has_wait:
        out.update(dispatch_capture="CAPTURED", replay_verified=False,
                   note="no wait_hidden_states; replay output not comparable")
        dump_exit(out, a.step_out, 0)
    try:
        g4.instantiate()
        torch.cuda.synchronize()
        repl_outs = []
        t = time.perf_counter()
        for _ in range(32):
            g4.replay()
            repl_outs.append(disp.wait_hidden_states())
        torch.cuda.synchronize()
        replay_s = time.perf_counter() - t
        eager_outs = []
        t = time.perf_counter()
        for _ in range(32):
            disp.set_inputs_with_invocation(h, mask, w)
            disp.dispatch_experts(0)
            eager_outs.append(disp.wait_hidden_states())
        torch.cuda.synchronize()
        eager_s = time.perf_counter() - t
        finite = all(bool(torch.isfinite(o).all().item()) for o in repl_outs
                     if isinstance(o, torch.Tensor))
        maxdiff = None
        compared = 0
        match = len(repl_outs) == len(eager_outs) == 32
        if match:
            for ro, eo in zip(repl_outs, eager_outs):
                if isinstance(ro, torch.Tensor) and isinstance(eo, torch.Tensor):
                    compared += 1
                    d = float((ro - eo).abs().max().item()) if ro.shape == eo.shape else float("inf")
                    maxdiff = d if maxdiff is None else max(maxdiff, d)
                else:
                    match = match and (ro is None and eo is None)
        # fix #8: vacuous pass impossible — 32 tensor pairs must compare and
        # maxdiff must be a real number within tolerance.
        verified = bool(match and finite and compared == 32
                        and maxdiff is not None and maxdiff <= 1e-4)
        rec(out, "replay_vs_eager", replay_ms=1000 * replay_s / 32,
            eager_ms=1000 * eager_s / 32, out_finite=finite,
            out_match=bool(match), compared=compared, max_abs_diff=maxdiff,
            replay_verified=verified)
        out.update(dispatch_capture="CAPTURED" if verified else "REPLAY-DIVERGED",
                   replay_verified=verified)
    except Exception as e:
        rec(out, "replay_vs_eager", ok=False, error=repr(e))
        out.update(dispatch_capture="FAIL@replay", replay_verified=False)
    dump_exit(out, a.step_out, 0)


# --------------------------- driver -------------------------------------------
def run_child(step, a):
    cmd = [sys.executable, os.path.abspath(__file__), "--step", step,
           "--step-out", os.path.join(a.out + ".step-" + step),
           "--model", a.model, "--offload", a.offload, "--policy", a.policy,
           "--ratio", str(a.ratio), "--threads", str(a.threads),
           "--gpu-route", a.gpu_route, "--prompts", a.prompts,
           "--max-new", str(a.max_new)]
    p = subprocess.run(cmd, stdout=open(a.out + ".step-" + step + ".log", "w"),
                       stderr=subprocess.STDOUT)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--offload", required=True)
    ap.add_argument("--policy", default="lcnu")
    ap.add_argument("--ratio", type=float, default=0.75)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--gpu-route", choices=["on", "off"], default="on")
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--max-new", type=int, default=64)
    ap.add_argument("--out", required=True)
    ap.add_argument("--step", choices=list(PROBES))
    ap.add_argument("--step-out")
    ap.add_argument("--hidden", type=int, default=2048)
    a = ap.parse_args()
    if a.step:
        {"pc": child_pc, "pinned": child_pinned, "hostfn": child_hostfn,
         "dispatch": child_dispatch}[a.step](a)
        os._exit(0)  # children always dump_exit; belt and braces

    out = {"probe": "exp753-cuda-graph-feasibility", "host": platform.node(),
           "driver": None, "steps": [], "child_rc": {}}
    try:
        import torch  # driver only reports identity; no CUDA work in-driver
        out["torch"] = torch.__version__
        out["cuda"] = torch.version.cuda
    except Exception as e:
        out["torch_err"] = repr(e)

    rc_total = 0
    missing = 0
    for step in PROBES:
        rc = run_child(step, a)
        out["child_rc"][step] = rc
        sf = a.out + ".step-" + step
        try:
            out["steps"].append(json.load(open(sf)))
        except Exception as e:
            out["steps"].append({"step": step, "error": f"result-missing:{e!r}", "rc": rc})
            missing += 1

    by = {s.get("step"): s for s in out["steps"]}
    pc = by.get("pc", {})
    out["positive_control"] = "OK" if pc.get("ok") else "FAIL"
    pn = by.get("pinned", {})
    out["pinned_capture"] = "CAPTURED" if pn.get("captured") else \
        f"FAIL:{pn.get('err_type') or pn.get('error', 'unknown')}"
    hf = by.get("hostfn", {})
    out["hostfn_capture"] = "CAPTURED" if hf.get("captured") and hf.get("replay_cb_fired", 0) > 0 \
        else "FAIL"
    out["hostfn_detail"] = {k: hf.get(k) for k in ("launch_rc", "launch_err", "replay_cb_fired", "error")}
    dp = by.get("dispatch", {})
    out["dispatch_capture"] = dp.get("dispatch_capture", "FAIL:NO-RESULT")
    out["replay_verified"] = dp.get("replay_verified", False)
    out["methods"] = dp.get("methods", {})
    out["dispatcher_found"] = dp.get("dispatcher_found", False)

    # fix #5: exit-code contract (PREREG §10.9): 3 = positive-control FAIL
    # (INCONCLUSIVE-ENV), 2 = probe crash (ANY nonzero child rc — includes
    # python exit 1 on unhandled exception and negative returncodes from
    # segfault/kill), 1 = result missing/undecodable with no crash,
    # 0 = all outcomes recorded (incl. genuine CAPTURE-FAIL).
    crashed = any(rc != 0 for rc in out["child_rc"].values())
    if out["positive_control"] != "OK":
        rc_total = 3
    elif crashed:
        rc_total = 2
    elif missing:
        rc_total = 1
    out["exit_code"] = rc_total
    json.dump(out, open(a.out, "w"), indent=1)
    print("DONE", a.out, "rc", rc_total, flush=True)
    sys.exit(rc_total)


if __name__ == "__main__":
    main()
