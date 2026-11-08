"""exp750 classifier tests, written from PREREG.md (the spec wins over the code).

Synthetic out/ dirs are built in tmp_path matching the formats classify750.py
and run_exp750.sh use: cells750.json in the parent of out/, <id>.json with
"rows" (out_ids/top16_ids/top16_vals/timed[{t1_s,t64_s,out_ids_64}]),
<id>.env, <id>.json.prov.json, monitor.csv `ts,cell,0, MiB0;1, MiB1;,ollama`,
precell.csv, rc.csv. Stdlib + pytest only. No network, no GPU.
"""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import classify750 as C  # noqa: E402

# arm -> (build, gpus, clb), mirroring cells750.json / PREREG arms table.
ARMSPEC = {
    "R1": ("U", "1", ""),
    "S1": ("F", "1", ""),
    "S0": ("F", "0", ""),
    "P2": ("F", "0,1", ""),
    "K2": ("P", "0,1", "1"),
    "C2": ("P", "0,1", ""),
    "H2": ("H", "0,1", ""),
}
# Default per-cell D (ms/token): q=D(K2)/D(P2)=1.2, s=D(S1)/D(R1)=1.0, u=D(S1)/D(P2)=1.0.
DEFAULT_D = {"R1": 10.0, "S1": 10.0, "S0": 10.0, "P2": 10.0, "K2": 12.0, "C2": 10.0, "H2": 10.0}
TREE = {"F": "moei-fix749", "P": "moei-fix740"}
STORE = {
    "U": "/home/u/moei-engine/MoE-Infinity/moe_infinity/_store.so",
    "F": "/home/u/moei-fix749/moe_infinity/_store.so",
    "P": "/home/u/moei-fix740/moe_infinity/_store.so",
    "H": None,
}
HAPPY = ["FIX-FASTER", "NOREGRESS-T", "NEUTRAL/MIXED", "PASS", "MANIP-OK"]


def ref_rows():
    rows = []
    for p in range(6):
        rows.append({
            "out_ids": [p * 1000 + j for j in range(64)],
            "top16_ids": [[p * 100 + j for j in range(16)] for _ in range(4)],
            "top16_vals": [[float(p) + j * 0.25 for j in range(16)] for _ in range(4)],
        })
    return rows


def make_rows(d_ms, quality="ref", drift=False, timer="ok"):
    """6 prompt rows; quality fields start as the reference, timed reps give d_ms per prompt."""
    rows = copy.deepcopy(ref_rows())
    if quality == "bad_out":
        rows[0]["out_ids"][0] += 777777
    elif quality == "bad_ids":
        rows[1]["top16_ids"][0][0] += 777777
    elif quality == "bad_vals":
        rows[2]["top16_vals"][0][0] += 777.0
    elif quality == "bad_all":
        for r in rows:
            r["out_ids"] = [x + 555555 for x in r["out_ids"]]
    for r in rows:
        reps = []
        for k in range(3):
            t1 = 0.01
            t64 = 0.01 + d_ms * 63.0 / 1000.0
            out = list(r["out_ids"])
            if drift and k == 0:
                out[0] += 999999
            if timer == "eq" and k == 1:
                t64 = t1
            if timer == "zero1" and k == 2:
                t1 = 0.0
            if timer == "lt" and k == 0:
                t64 = t1 / 2.0
            reps.append({"t1_s": t1, "t64_s": t64, "out_ids_64": out})
        r["timed"] = reps
    return rows


def memstr(m):
    return ";".join(f"{g}, {v}" for g, v in sorted(m.items())) + ";"


def celldefs():
    defs = []
    for b in (1, 2, 3):
        for arm, (build, gpus, clb) in ARMSPEC.items():
            defs.append({"id": f"b{b}_{arm}", "arm": arm, "block": b, "build": build,
                         "gpus": gpus, "ratio": 0.2, "policy": "lcnu", "clb": clb})
    return defs


class Run:
    """Builds <tmp>/run/{cells750.json, ref.json, out/...} cell by cell."""

    def __init__(self, tmp_path):
        self.root = tmp_path / "run"
        self.out = self.root / "out"
        self.out.mkdir(parents=True)
        self.defs = celldefs()
        self.by_id = {c["id"]: c for c in self.defs}
        self.rc, self.pre, self.mon = [], [], []
        self.ref = self.root / "ref.json"
        self.ref.write_text(json.dumps({"rows": ref_rows()}))

    def add(self, cid, d=None, quality="ref", drift=False, timer="ok", ollama=0,
            mon_mem=None, pre_mem=None, clb=None, prov="ok", store="ok", rc="0",
            write_json=True, write_env=True, write_prov=True, monitor=True,
            precell=True, raw_json=None):
        base = cid[:-2] if cid.endswith("_x") else cid
        cdef = self.by_id[base]
        build = cdef["build"]
        if d is None:
            d = DEFAULT_D[cdef["arm"]]
        if raw_json is not None:
            (self.out / f"{cid}.json").write_text(raw_json)
        elif write_json:
            so = STORE[build]
            if store == "wrong":
                so = ("/home/u/moei-fix749/moe_infinity/_store.so" if build == "P"
                      else "/home/u/moei-fix740/moe_infinity/_store.so")
            cell = {"rows": make_rows(d, quality, drift, timer), "store_so": so}
            (self.out / f"{cid}.json").write_text(json.dumps(cell))
        if write_env:
            v = cdef["clb"] if clb is None else clb
            (self.out / f"{cid}.env").write_text(
                f"CUDA_LAUNCH_BLOCKING={v}\nCUDA_DEVICE_ORDER=\n")
        if write_prov and build in ("F", "P"):
            tree = TREE[build]
            if prov == "wrong":
                tree = "moei-fix740" if build == "F" else "moei-fix749"
            p = {"moe_infinity": f"/home/u/{tree}/moe_infinity/__init__.py",
                 "store_so": f"/home/u/{tree}/moe_infinity/_store.so"}
            (self.out / f"{cid}.json.prov.json").write_text(json.dumps(p))
        if rc is not None:
            self.rc.append(f"{cid},{rc}")
        pm = pre_mem or {0: 100, 1: 100}
        mm = mon_mem or {0: 100, 1: 100}
        if precell:
            self.pre.append(f"{cid},{memstr(pm)},0")
        if monitor:
            self.mon.append(f"2026-11-07T00:00:00Z,{cid},{memstr(mm)},{ollama}")

    def add_all(self, overrides=None, ds=None):
        overrides = overrides or {}
        for c in self.defs:
            kw = dict(overrides.get(c["id"], {}))
            if ds:
                if (c["arm"], c["block"]) in ds:
                    kw.setdefault("d", ds[(c["arm"], c["block"])])
                elif c["arm"] in ds:
                    kw.setdefault("d", ds[c["arm"]])
            if c["arm"] == "C2":
                kw.setdefault("quality", "bad_all")  # C2 is the known-corrupt control
            self.add(c["id"], **kw)

    def finish(self, monitor_extra=(), write_monitor=True, write_precell=True, write_rc=True):
        (self.root / "cells750.json").write_text(json.dumps(self.defs))
        if write_rc:
            (self.out / "rc.csv").write_text("\n".join(self.rc) + "\n")
        if write_precell:
            (self.out / "precell.csv").write_text("\n".join(self.pre) + "\n")
        if write_monitor:
            (self.out / "monitor.csv").write_text(
                "\n".join(list(self.mon) + list(monitor_extra)) + "\n")
        return self.out, self.ref


def classify(capsys, out, ref):
    rc = C.main(["classify750.py", str(out), str(ref)])
    text = capsys.readouterr().out
    assert rc == 0
    return text


def verdict_fields(text):
    lines = [ln for ln in text.splitlines() if ln.startswith("VERDICT750 ")]
    assert len(lines) == 1, text
    body = lines[0][len("VERDICT750 "):]
    main_part, _, flags = body.partition(" flags: ")
    return main_part.split("|"), flags, lines[0]


def happy_run(tmp_path, capsys, overrides=None, ds=None, **finish_kw):
    run = Run(tmp_path)
    run.add_all(overrides=overrides, ds=ds)
    out, ref = run.finish(**finish_kw)
    return run, classify(capsys, out, ref)


# --- G-Q unit rules (PREREG lines 47-49) -------------------------------------------------------

def _refkey():
    return C.rows_key({"rows": ref_rows()})


def test_quality_matches_all_six():
    cell = {"rows": make_rows(10.0)}
    assert C.quality_matches(cell, _refkey()) == 6


@pytest.mark.parametrize("quality", ["bad_out", "bad_ids", "bad_vals"])
def test_quality_matches_single_field_diff_fails_that_prompt(quality):
    # Any one of out_ids / top16_ids / top16_vals differing on one prompt -> not 6/6.
    cell = {"rows": make_rows(10.0, quality=quality)}
    assert C.quality_matches(cell, _refkey()) == 5


def test_quality_matches_wrong_row_count_is_not_a_pass():
    cell = {"rows": make_rows(10.0)[:5]}
    assert C.quality_matches(cell, _refkey()) != 6


def test_quality_matches_missing_ref_is_not_a_pass():
    assert C.quality_matches({"rows": make_rows(10.0)}, None) is None


# --- G-T / G-V unit rules (PREREG lines 50-52) -------------------------------------------------

def test_timed_identity_ok():
    assert C.timed_identity({"rows": make_rows(10.0)}) is True


def test_timed_identity_one_drifted_rep_fails():
    rows = make_rows(10.0)
    rows[3]["timed"][2]["out_ids_64"] = list(rows[3]["out_ids"])
    rows[3]["timed"][2]["out_ids_64"][10] += 1
    assert C.timed_identity({"rows": rows}) is False


def test_timed_identity_missing_timed_fails_closed():
    assert C.timed_identity({"rows": ref_rows()}) is None


def test_timer_sane_ok():
    assert C.timer_sane({"rows": make_rows(10.0)}) is True


@pytest.mark.parametrize("t1,t64", [(0.5, 0.5), (0.5, 0.4), (0.0, 0.5), (-0.1, 0.5), (0.5, 0.0)])
def test_timer_sane_bad_rep_fails(t1, t64):
    rows = make_rows(10.0)
    rows[0]["timed"][1]["t1_s"] = t1
    rows[0]["timed"][1]["t64_s"] = t64
    assert C.timer_sane({"rows": rows}) is False


def test_timer_sane_missing_timed_fails_closed():
    assert C.timer_sane({"rows": ref_rows()}) is None


# --- Metric (PREREG lines 43-44): d_p = median_rep((t64-t1)/63) ms, D = median over prompts ---

def _row(reps, n=64):
    return {"out_ids": [7] * n,
            "timed": [{"t1_s": t1, "t64_s": t64, "out_ids_64": [7] * n} for t1, t64 in reps]}


def test_prompt_d_ms_hand_computed():
    # diffs 0.63, 1.26, 0.945 s -> 10, 20, 15 ms/token -> median 15.
    row = _row([(0.01, 0.64), (0.01, 1.27), (0.01, 0.955)])
    assert C.prompt_d_ms(row) == pytest.approx(15.0, abs=1e-6)


def test_prompt_d_ms_divides_by_63_not_by_output_length():
    # PREREG formula is literally (t64-t1)/63. A short timed run must not rescale it.
    row = _row([(0.01, 0.64)], n=2)
    assert C.prompt_d_ms(row) == pytest.approx(10.0, abs=1e-6)


def test_cell_DE_median_over_prompts_hand_computed():
    rows = []
    for d in (10.0, 20.0, 30.0, 40.0, 50.0, 60.0):
        rows.append(_row([(0.01, 0.01 + d * 63.0 / 1000.0)]))
    D, E = C.cell_DE({"rows": rows})
    assert D == pytest.approx(35.0, abs=1e-6)          # median of 10..60
    # e_p = t64/64: rows for d=30,40 have t64 1.90, 2.53 -> median E = (1.90+2.53)/2/64*1000
    assert E == pytest.approx(34.609375, abs=1e-6)


def test_cell_DE_unusable_row_fails_closed():
    rows = make_rows(10.0)
    rows[0]["timed"] = []
    assert C.cell_DE({"rows": rows}) == (None, None)


# --- Decision thresholds at exact boundaries (PREREG lines 62-67) -----------------------------

@pytest.mark.parametrize("qs,expected", [
    ([1.10, 1.10, 1.10], "FIX-FASTER"),          # >= 1.10 inclusive
    ([1.0999, 1.0999, 1.0999], "MIXED"),         # just under is NOT FIX-FASTER
    ([0.91, 0.91, 0.91], "WORKAROUND-FASTER"),   # <= 0.91 inclusive
    ([0.9101, 0.9101, 0.9101], "MIXED"),
    ([0.95, 1.05, 1.00], "EQUIVALENT"),          # 0.95..1.05 inclusive
    ([1.0501, 1.0501, 1.0501], "MIXED"),
    ([0.9499, 0.9499, 0.9499], "MIXED"),
    ([1.20, 1.20, 1.00], "MIXED"),               # mixed blocks
    ([1.20, 0.80, 1.20], "MIXED"),
])
def test_decide_d1_boundaries(qs, expected):
    assert C.decide_d1(qs) == expected


@pytest.mark.parametrize("ss,expected", [
    ([0.95, 1.05, 1.00], "NOREGRESS-T"),         # inclusive band
    ([1.05, 1.05, 1.05], "NOREGRESS-T"),         # 1.05 is not REGRESS (needs > 1.05)
    ([0.95, 0.95, 0.95], "NOREGRESS-T"),         # 0.95 is not FASTER (needs < 0.95)
    ([1.0501, 1.0501, 1.0501], "REGRESS-T"),
    ([0.9499, 0.9499, 0.9499], "FASTER-T"),
    ([1.06, 1.06, 1.00], "UNRESOLVED-T"),        # mixed blocks
    ([0.90, 1.10, 1.00], "UNRESOLVED-T"),
])
def test_decide_d2_boundaries(ss, expected):
    assert C.decide_d2(ss) == expected


@pytest.mark.parametrize("us,expected", [
    ([1.10, 1.10, 1.10], "TWO-GPU-FASTER"),
    ([1.0999, 1.0999, 1.0999], "NEUTRAL/MIXED"),
    ([0.91, 0.91, 0.91], "TWO-GPU-SLOWER"),
    ([0.9101, 0.9101, 0.9101], "NEUTRAL/MIXED"),
    ([1.00, 1.00, 1.00], "NEUTRAL/MIXED"),
    ([1.20, 0.80, 1.20], "NEUTRAL/MIXED"),
])
def test_decide_d3_boundaries(us, expected):
    assert C.decide_d3(us) == expected


def test_decide_empty_ratios_is_never_a_favourable_verdict():
    # PREREG requires the ratio condition in 3/3 blocks; zero ratios prove nothing.
    assert C.decide_d1([]) not in ("FIX-FASTER", "WORKAROUND-FASTER", "EQUIVALENT")
    assert C.decide_d2([]) not in ("NOREGRESS-T", "REGRESS-T", "FASTER-T")
    assert C.decide_d3([]) not in ("TWO-GPU-FASTER", "TWO-GPU-SLOWER")


# --- G-F parsing + rule units (PREREG lines 55-59) ----------------------------------------------

def test_parse_monitor_and_precell_lines():
    assert C.parse_monitor_line("2026-11-07T00:00:00Z,b1_R1,0, 123;1, 456;,2") == (
        "b1_R1", {0: 123, 1: 456}, 2)
    assert C.parse_precell_line("b1_R1,0, 123;1, 456;,0") == ("b1_R1", {0: 123, 1: 456}, 0)
    assert C.parse_monitor_line("not a monitor line") is None
    assert C.parse_precell_line("b1_R1,garbage") is None


def _fs(mem, oll=0, gpus="1", pre=None, bad=None, cid="c"):
    samples = {cid: [(mem, oll)]}
    return C.foreign_status(cid, gpus, samples, pre or {cid: {0: 100, 1: 100}}, bad or [])


def test_foreign_status_ollama_ge_1():
    assert _fs({0: 100, 1: 100}, oll=1) == "FOREIGN"


def test_foreign_status_unassigned_mem_over_slack():
    assert _fs({0: 613, 1: 100}) == "FOREIGN"          # precell 100 + 513


def test_foreign_status_unassigned_mem_exactly_plus_512_is_clean():
    assert _fs({0: 612, 1: 100}) == "CLEAN"             # > precell+512 is the rule, not >=


def test_foreign_status_assigned_gpu_growth_is_clean():
    assert _fs({0: 100, 1: 99999}) == "CLEAN"           # GPU1 is assigned to this cell


def test_foreign_status_two_gpu_cell_has_no_unassigned_gpu():
    assert _fs({0: 99999, 1: 99999}, gpus="0,1") == "CLEAN"


def test_foreign_status_unknown_inputs_are_never_clean():
    assert C.foreign_status("c", "1", {}, {"c": {0: 100}}, []) != "CLEAN"        # no samples
    assert C.foreign_status("c", "1", {"c": [({0: 1}, 0)]}, {}, []) != "CLEAN"    # no precell
    assert _fs({0: 100, 1: 100}, bad=["garbage line"]) != "CLEAN"                 # malformed monitor


def test_cv_zero_for_constant_and_positive_for_spread():
    assert C.cv([10.0, 10.0, 10.0]) == 0.0
    assert C.cv([10.0, 10.0, 20.0]) > 0.05
    assert C.cv([10.0, 10.0, 10.1]) < 0.05


# --- Full-run integration via main() -------------------------------------------------------------
# Default fixture: D(K2)=12, all other arms 10 -> D1 FIX-FASTER, D2 NOREGRESS-T, D3 NEUTRAL/MIXED.

def test_happy_path_verdict_line_is_final_and_exact(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys)
    fields, flags, line = verdict_fields(text)
    assert fields == HAPPY
    assert line == "VERDICT750 FIX-FASTER|NOREGRESS-T|NEUTRAL/MIXED|PASS|MANIP-OK"
    assert text.rstrip().splitlines()[-1] == line
    assert "NOISY" not in flags and "C2-UNEXPECTED-CLEAN" not in flags


def test_verdict_line_format(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys)
    _, _, line = verdict_fields(text)
    assert re.fullmatch(
        r"VERDICT750 [^|\s]+\|[^|\s]+\|[^|\s]+\|[^|\s]+\|[^|\s]+( flags: .+)?", line)


def test_ratio_direction_k2_faster_means_workaround_faster(tmp_path, capsys):
    # D is ms/token (lower = faster); q = D(K2)/D(P2) = 5/10 <= 0.91 in 3/3 blocks.
    _, text = happy_run(tmp_path, capsys, ds={"K2": 5.0})
    assert verdict_fields(text)[0][0] == "WORKAROUND-FASTER"


def test_s1_slower_is_regress_and_two_gpu_faster(tmp_path, capsys):
    # s = D(S1)/D(R1) = 1.2 > 1.05; u = D(S1)/D(P2) = 1.2 >= 1.10.
    _, text = happy_run(tmp_path, capsys, ds={"S1": 12.0})
    fields = verdict_fields(text)[0]
    assert fields[1] == "REGRESS-T"
    assert fields[2] == "TWO-GPU-FASTER"


# G-Q integration (PREREG lines 47-49)

def test_gq_top16_vals_diff_voids_only_decisions_using_the_arm(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_P2": {"quality": "bad_vals"}})
    fields = verdict_fields(text)[0]
    assert fields == ["VOID", "NOREGRESS-T", "VOID", "QUALITY-FAIL(P2)", "MANIP-OK"]


def test_gq_out_ids_diff_on_r1_voids_d2_only(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b2_R1": {"quality": "bad_out"}})
    fields = verdict_fields(text)[0]
    assert fields[0] == "FIX-FASTER" and fields[1] == "VOID"
    assert fields[3] == "QUALITY-FAIL(R1)"


def test_gq_s0_failure_voids_no_decision_but_is_reported(tmp_path, capsys):
    # S0 feeds no D1/D2/D3 ratio (descriptive link ratio only), so no decision is VOID.
    _, text = happy_run(tmp_path, capsys, overrides={"b1_S0": {"quality": "bad_out"}})
    fields = verdict_fields(text)[0]
    assert fields[:3] == HAPPY[:3]
    assert fields[3] == "QUALITY-FAIL(S0)"


def test_c2_quality_failure_never_gates(tmp_path, capsys):
    ov = {f"b{b}_C2": {"quality": "bad_all"} for b in (1, 2, 3)}
    _, text = happy_run(tmp_path, capsys, overrides=ov)
    assert verdict_fields(text)[0] == HAPPY


def test_h2_quality_is_not_gated(tmp_path, capsys):
    ov = {f"b{b}_H2": {"quality": "bad_all"} for b in (1, 2, 3)}
    _, text = happy_run(tmp_path, capsys, overrides=ov)
    assert verdict_fields(text)[0] == HAPPY


def test_c2_unexpected_clean_flag_when_clean_in_all_blocks(tmp_path, capsys):
    ov = {f"b{b}_C2": {"quality": "ref"} for b in (1, 2, 3)}
    _, text = happy_run(tmp_path, capsys, overrides=ov)
    fields, flags, _ = verdict_fields(text)
    assert fields == HAPPY
    assert "C2-UNEXPECTED-CLEAN" in flags


def test_c2_no_unexpected_clean_flag_when_one_block_dirty(tmp_path, capsys):
    ov = {"b1_C2": {"quality": "ref"}, "b2_C2": {"quality": "ref"}}  # b3 stays corrupt
    _, text = happy_run(tmp_path, capsys, overrides=ov)
    assert "C2-UNEXPECTED-CLEAN" not in verdict_fields(text)[1]


# G-T / G-V integration (PREREG lines 50-52)

def test_timed_drift_excludes_cell_and_blocks_its_decisions(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b2_P2": {"drift": True}})
    fields, flags, _ = verdict_fields(text)
    assert "P2:EXCLUDED(b2_P2:TIMED-DRIFT)" in flags
    assert fields[0] == "INCOMPLETE" and fields[2] == "INCOMPLETE"
    assert fields[1] == "NOREGRESS-T"


def test_c2_timed_drift_is_exempt(tmp_path, capsys):
    ov = {f"b{b}_C2": {"drift": True} for b in (1, 2, 3)}
    _, text = happy_run(tmp_path, capsys, overrides=ov)
    fields, flags, _ = verdict_fields(text)
    assert fields == HAPPY
    assert "C2:EXCLUDED" not in flags


def test_timer_invalid_t64_eq_t1_excludes_cell(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_K2": {"timer": "eq"}})
    fields, flags, _ = verdict_fields(text)
    assert "K2:EXCLUDED(b1_K2:TIMER-INVALID)" in flags
    assert fields[0] == "INCOMPLETE"


def test_timer_invalid_t1_zero_excludes_cell(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b3_S1": {"timer": "zero1"}})
    fields, flags, _ = verdict_fields(text)
    assert "S1:EXCLUDED(b3_S1:TIMER-INVALID)" in flags
    assert fields[1] == "INCOMPLETE" and fields[2] == "INCOMPLETE"


# G-M integration (PREREG lines 53-54): any mismatch -> whole run VOID

def test_gm_k2_clb_not_1_voids_run(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_K2": {"clb": ""}})
    assert verdict_fields(text)[0] == ["VOID", "VOID", "VOID", "PASS", "MANIP-FAIL"]


def test_gm_non_k2_clb_set_voids_run(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b2_S1": {"clb": "1"}})
    fields = verdict_fields(text)[0]
    assert fields[:3] == ["VOID", "VOID", "VOID"] and fields[4] == "MANIP-FAIL"


def test_gm_wrong_prov_tree_for_fix749_arm_voids_run(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_P2": {"prov": "wrong"}})
    fields = verdict_fields(text)[0]
    assert fields[:3] == ["VOID", "VOID", "VOID"] and fields[4] == "MANIP-FAIL"


def test_gm_missing_prov_for_fix740_arm_voids_run(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_K2": {"write_prov": False}})
    assert verdict_fields(text)[0][4] == "MANIP-FAIL"


def test_gm_missing_env_file_voids_run(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_R1": {"write_env": False}})
    assert verdict_fields(text)[0][4] == "MANIP-FAIL"


def test_gm_cell_store_so_wrong_tree_voids_run(tmp_path, capsys):
    # Cell JSON records the loaded _store.so under the fix740 tree for a fix749 (F) arm,
    # even though the prov file claims fix749. PREREG: provenance store_so must match.
    _, text = happy_run(tmp_path, capsys, overrides={"b1_P2": {"store": "wrong"}})
    assert verdict_fields(text)[0][4] == "MANIP-FAIL"


def test_gm_no_cells_at_all_is_never_manip_ok(tmp_path):
    run = Run(tmp_path)
    run.finish()
    gm, _bad = C.manip(run.out, run.defs)
    assert gm != "MANIP-OK"


# G-F integration (PREREG lines 55-59)

def test_foreign_ollama_sample_excludes_cell(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_S1": {"ollama": 1}})
    fields, flags, _ = verdict_fields(text)
    assert "S1:EXCLUDED(b1_S1:FOREIGN)" in flags
    assert fields[1] == "INCOMPLETE" and fields[2] == "INCOMPLETE"
    assert fields[0] == "FIX-FASTER"


def test_foreign_unassigned_mem_plus_513_excludes_cell(tmp_path, capsys):
    ov = {"b1_S1": {"mon_mem": {0: 613, 1: 100}}}  # S1 uses GPU1 only; GPU0 precell 100
    _, text = happy_run(tmp_path, capsys, overrides=ov)
    fields, flags, _ = verdict_fields(text)
    assert "S1:EXCLUDED(b1_S1:FOREIGN)" in flags
    assert fields[1] == "INCOMPLETE"


def test_unassigned_mem_exactly_plus_512_is_not_foreign(tmp_path, capsys):
    ov = {"b1_S1": {"mon_mem": {0: 612, 1: 100}}}
    _, text = happy_run(tmp_path, capsys, overrides=ov)
    assert verdict_fields(text)[0] == HAPPY


def test_assigned_gpu_mem_growth_is_not_foreign(tmp_path, capsys):
    ov = {"b1_S1": {"mon_mem": {0: 100, 1: 99999}}}
    _, text = happy_run(tmp_path, capsys, overrides=ov)
    assert verdict_fields(text)[0] == HAPPY


def test_malformed_monitor_line_yields_no_clean_pass(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, monitor_extra=["this is not a monitor line"])
    fields = verdict_fields(text)[0]
    assert fields[:3] == ["INCOMPLETE", "INCOMPLETE", "INCOMPLETE"]
    assert "malformed monitor" in text


def test_missing_monitor_file_fails_closed(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, write_monitor=False)
    assert verdict_fields(text)[0][:3] == ["INCOMPLETE"] * 3


def test_missing_precell_for_cell_fails_closed(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_P2": {"precell": False}})
    fields = verdict_fields(text)[0]
    assert fields[0] == "INCOMPLETE" and fields[2] == "INCOMPLETE"


# _x replacement + INCOMPLETE (PREREG lines 57-59)

def test_clean_x_replaces_foreign_original(tmp_path, capsys):
    run = Run(tmp_path)
    run.add_all(overrides={"b1_P2": {"ollama": 1}})
    run.add("b1_P2_x")  # clean rerun, default D for P2
    out, ref = run.finish()
    text = classify(capsys, out, ref)
    fields, flags, _ = verdict_fields(text)
    assert "REPLACED-BY b1_P2_x" in text
    assert fields == HAPPY
    assert "P2:EXCLUDED" not in flags


def test_dirty_x_does_not_replace_foreign_original(tmp_path, capsys):
    run = Run(tmp_path)
    run.add_all(overrides={"b1_P2": {"ollama": 1}})
    run.add("b1_P2_x", ollama=1)  # rerun is itself FOREIGN
    out, ref = run.finish()
    text = classify(capsys, out, ref)
    fields = verdict_fields(text)[0]
    assert "REPLACED-BY" not in text
    assert fields[0] == "INCOMPLETE" and fields[2] == "INCOMPLETE"


def test_drifted_x_does_not_replace_foreign_original(tmp_path, capsys):
    run = Run(tmp_path)
    run.add_all(overrides={"b1_P2": {"ollama": 1}})
    run.add("b1_P2_x", drift=True)
    out, ref = run.finish()
    text = classify(capsys, out, ref)
    assert verdict_fields(text)[0][0] == "INCOMPLETE"


def test_clean_x_does_not_replace_a_clean_original(tmp_path, capsys):
    run = Run(tmp_path)
    run.add_all()
    run.add("b1_P2_x", d=99.0)  # would flip D1 if (wrongly) used
    out, ref = run.finish()
    text = classify(capsys, out, ref)
    assert "REPLACED-BY" not in text
    assert verdict_fields(text)[0] == HAPPY


def test_replaced_foreign_original_bad_quality_still_fails_arm_A2(tmp_path, capsys):
    # A2: G-Q is strict — every G-Q cell that ran (original AND _x) must match the
    # reference. A clean, quality-matching _x replacing the FOREIGN original for timing
    # does NOT forgive the original's mismatch: P2 is QUALITY-FAIL, D1/D3 VOID.
    run = Run(tmp_path)
    run.add_all(overrides={"b1_P2": {"ollama": 1, "quality": "bad_vals"}})
    run.add("b1_P2_x")
    out, ref = run.finish()
    text = classify(capsys, out, ref)
    assert verdict_fields(text)[0] == ["VOID", "NOREGRESS-T", "VOID",
                                         "QUALITY-FAIL(P2)", "MANIP-OK"]


def test_quality_bad_x_also_fails_arm_A2(tmp_path, capsys):
    # A2 covers the _x cell too: a FOREIGN original with matching quality, rerun as a
    # timing-clean but quality-bad _x, still makes P2 QUALITY-FAIL and voids D1/D3.
    run = Run(tmp_path)
    run.add_all(overrides={"b1_P2": {"ollama": 1}})
    run.add("b1_P2_x", quality="bad_out")
    out, ref = run.finish()
    text = classify(capsys, out, ref)
    assert verdict_fields(text)[0] == ["VOID", "NOREGRESS-T", "VOID",
                                         "QUALITY-FAIL(P2)", "MANIP-OK"]


def test_clean_x_counts_when_original_is_missing(tmp_path, capsys):
    # A decision needs a clean cell per arm per block (PREREG line 58-59); a clean _x
    # for that arm/block is such a cell even if the original never produced output.
    run = Run(tmp_path)
    run.add_all(overrides={"b1_P2": {"write_json": False}})
    run.add("b1_P2_x")
    out, ref = run.finish()
    text = classify(capsys, out, ref)
    assert verdict_fields(text)[0] == HAPPY


def test_missing_clean_cell_for_arm_in_one_block_is_incomplete(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b3_K2": {"write_json": False}})
    fields, flags, _ = verdict_fields(text)
    assert fields[0] == "INCOMPLETE"
    assert fields[1] == "NOREGRESS-T" and fields[2] == "NEUTRAL/MIXED"
    assert "INCOMPLETE" in flags


def test_list_reruns_names_only_dirty_originals(tmp_path, capsys):
    run = Run(tmp_path)
    run.add_all(overrides={
        "b1_S1": {"ollama": 1},          # FOREIGN
        "b2_P2": {"drift": True},        # TIMED-DRIFT
        "b3_K2": {"timer": "eq"},        # TIMER-INVALID
    })
    out, _ref = run.finish()
    rc = C.main(["classify750.py", str(out), "--list-reruns"])
    lines = capsys.readouterr().out.split()
    assert rc == 0
    assert set(lines) == {"b1_S1", "b2_P2", "b3_K2"}


# NOISY (PREREG lines 68-69) and fail-closed inputs (PREREG line 70 + brief)

def test_noisy_flag_when_r1_cv_exceeds_5pct_verdict_text_kept(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, ds={("R1", 3): 16.0})  # R1 D = 10, 10, 16
    fields, flags, _ = verdict_fields(text)
    assert "NOISY" in flags.split()
    assert fields[0] == "FIX-FASTER"  # verdict text kept, only flagged


def test_missing_reference_fails_closed_never_passes(tmp_path, capsys):
    run = Run(tmp_path)
    run.add_all()
    out, _ref = run.finish()
    text = classify(capsys, out, run.root / "does_not_exist.json")
    fields = verdict_fields(text)[0]
    assert fields[:4] == ["INCOMPLETE"] * 4


def test_malformed_cell_json_fails_closed(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_R1": {"raw_json": "{not json"}})
    fields = verdict_fields(text)[0]
    assert fields[1] == "INCOMPLETE"
    assert fields[3] != "PASS"


def test_nonzero_rc_cell_is_not_present(tmp_path, capsys):
    _, text = happy_run(tmp_path, capsys, overrides={"b1_R1": {"rc": "3"}})
    assert verdict_fields(text)[0][1] == "INCOMPLETE"


def test_empty_out_dir_never_passes(tmp_path, capsys):
    run = Run(tmp_path)
    out, ref = run.finish()
    text = classify(capsys, out, ref)
    fields = verdict_fields(text)[0]
    assert fields[:4] == ["INCOMPLETE"] * 4


def test_missing_cells750_never_passes(tmp_path, capsys):
    # A malformed cells750.json in the run dir must never yield a pass: either the
    # classifier reports INCOMPLETE outright, or any fallback cell list finds no
    # cells in this empty out/ and likewise stays INCOMPLETE.
    run = Run(tmp_path)
    out, ref = run.finish()
    (run.root / "cells750.json").write_text("{broken")
    text = classify(capsys, out, ref)
    fields = verdict_fields(text)[0]
    assert "PASS" not in fields and fields[0] in ("INCOMPLETE", "VOID")





