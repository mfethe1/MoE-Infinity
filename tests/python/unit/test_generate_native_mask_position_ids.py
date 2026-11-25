"""MoE.generate() native path must honour attention_mask / position_ids.

The native engine path (use_native_engine=True, batch-1 2D input) used to
build ``prompt_token_ids`` from ``input_ids[0]`` and silently drop
``attention_mask`` and ``position_ids``. The required behavior is:

* attention_mask is checked first, in order: shape must equal input_ids
  shape ("attention_mask shape"); values must all be 0 or 1
  ("must be 0/1 valued"); an all-zero mask is rejected ("entire prompt");
  then masked-out tokens are trimmed from the ENGINE prompt in original
  order. The RETURNED tensor is still the FULL input row + engine output
  ids (matching DFlash and the HF path), so ``out[:, L:]`` is the
  continuation.
* position_ids is checked next: shape must equal input_ids shape
  ("position_ids shape"). At positions kept by the mask, values must match
  ``[0..K-1]`` (K = kept token count), as in HuggingFace's default positions;
  anything else is rejected ("position_ids is not supported on the native").
  Without a mask, this is the full-length default ``[0..L-1]``. The comparison
  must not truncate: integral float ids are accepted, fractional ones are
  rejected.
* Every ValueError raise path is side-effect free: ``_configure_hook`` and
  the native engine are never called.
* The HF path (use_native_engine=False) forwards both kwargs unchanged.
"""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

pytest.importorskip("torch")

import torch

from moe_infinity.engine.types import SamplingParams

ENGINE_OUTPUT = [9, 9]
INPUT_ROW = [5, 6, 7, 8]


class _FakeResult:
    def __init__(self):
        self.output_token_ids = list(ENGINE_OUTPUT)


class FakeNativeEngine:
    def __init__(self):
        self.calls: list[dict] = []
        self.spec_strategy = None

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResult()


class FakeHFModel:
    def __init__(self):
        self.calls: list[tuple[torch.Tensor, dict]] = []

    def eval(self):
        return self

    def generate(self, input_ids, **kwargs):
        self.calls.append((input_ids, kwargs))
        extra = torch.tensor([ENGINE_OUTPUT], dtype=input_ids.dtype)
        return torch.cat([input_ids, extra], dim=1)


def _make_moe(use_native_engine: bool = True):
    from moe_infinity.entrypoints.big_modeling import MoE

    instance = MoE.__new__(MoE)
    instance.model = FakeHFModel()
    instance._configure_hook = MagicMock()
    instance._cached_past_key_values = None
    instance.max_seq_length = 1024
    instance.use_native_engine = use_native_engine
    if use_native_engine:
        instance._native_generation_engine = FakeNativeEngine()
    else:
        instance._native_generation_engine = None
        instance._resolve_native_input_device = lambda: torch.device("cpu")
    return instance


def _input_ids():
    return torch.tensor([INPUT_ROW], dtype=torch.long)


def _generate(moe, input_ids, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return moe.generate(input_ids, max_new_tokens=2, **kwargs)


def _only_engine_call(moe):
    calls = moe._native_generation_engine.calls
    assert len(calls) == 1, f"expected one engine call, got {len(calls)}"
    return calls[0]


# --- attention_mask shape ----------------------------------------------------


@pytest.mark.parametrize(
    "mask",
    [
        torch.tensor([[1, 1, 1]], dtype=torch.long),
        torch.tensor([1, 1, 1, 1], dtype=torch.long),
        torch.tensor([[1, 1, 1, 1], [1, 1, 1, 1]], dtype=torch.long),
    ],
    ids=["short", "1d", "batch2"],
)
def test_attention_mask_shape_mismatch_raises(mask):
    moe = _make_moe()
    with pytest.raises(ValueError, match="attention_mask shape"):
        _generate(moe, _input_ids(), attention_mask=mask)


# --- all-zero attention_mask -------------------------------------------------


def test_all_zero_attention_mask_raises():
    moe = _make_moe()
    mask = torch.zeros((1, 4), dtype=torch.long)
    with pytest.raises(ValueError, match="entire prompt"):
        _generate(moe, _input_ids(), attention_mask=mask)


# --- attention_mask holes are trimmed ----------------------------------------


def test_attention_mask_holes_trim_prompt_in_order():
    moe = _make_moe()
    mask = torch.tensor([[1, 1, 0, 1]], dtype=torch.long)

    out = _generate(moe, _input_ids(), attention_mask=mask)

    call = _only_engine_call(moe)
    assert set(call.keys()) == {"prompt_token_ids", "sampling_params"}
    assert list(call["prompt_token_ids"]) == [5, 6, 8]
    assert isinstance(call["sampling_params"], SamplingParams)
    assert isinstance(out, torch.Tensor)
    # Return the FULL input row + engine output, not the trimmed prompt, so
    # out[:, input_ids.shape[1]:] is the continuation.
    assert out.tolist() == [INPUT_ROW + ENGINE_OUTPUT]


# --- all-ones attention_mask == no mask --------------------------------------


def test_all_ones_attention_mask_matches_no_mask_call():
    baseline = _make_moe()
    base_out = _generate(baseline, _input_ids())
    base_call = _only_engine_call(baseline)

    moe = _make_moe()
    out = _generate(
        moe, _input_ids(), attention_mask=torch.ones((1, 4), dtype=torch.long)
    )
    call = _only_engine_call(moe)

    assert set(call.keys()) == set(base_call.keys())
    assert list(call["prompt_token_ids"]) == list(base_call["prompt_token_ids"])
    assert list(call["prompt_token_ids"]) == INPUT_ROW
    assert call["sampling_params"] == base_call["sampling_params"]
    assert torch.equal(out, base_out)


# --- default position_ids accepted -------------------------------------------


def test_default_position_ids_accepted():
    moe = _make_moe()
    position_ids = torch.arange(4, dtype=torch.long).unsqueeze(0)

    out = _generate(moe, _input_ids(), position_ids=position_ids)

    call = _only_engine_call(moe)
    assert set(call.keys()) == {"prompt_token_ids", "sampling_params"}
    assert list(call["prompt_token_ids"]) == INPUT_ROW
    assert out.tolist() == [INPUT_ROW + ENGINE_OUTPUT]


# --- non-default position_ids rejected ---------------------------------------


def test_non_default_position_ids_raise():
    moe = _make_moe()
    position_ids = torch.tensor([[10, 11, 12, 13]], dtype=torch.long)
    with pytest.raises(
        ValueError, match="position_ids is not supported on the native"
    ):
        _generate(moe, _input_ids(), position_ids=position_ids)


def test_position_ids_compared_against_full_length_after_mask_trim():
    moe = _make_moe()
    mask = torch.tensor([[1, 1, 0, 1]], dtype=torch.long)
    full = torch.arange(4, dtype=torch.long).unsqueeze(0)
    with pytest.raises(
        ValueError, match="position_ids is not supported on the native"
    ):
        _generate(moe, _input_ids(), attention_mask=mask, position_ids=full)


def test_hf_default_position_ids_accepted_after_mask_trim():
    moe = _make_moe()
    mask = torch.tensor([[1, 1, 0, 1]], dtype=torch.long)
    hf_default = torch.tensor([[0, 1, 0, 2]], dtype=torch.long)

    _generate(moe, _input_ids(), attention_mask=mask, position_ids=hf_default)

    assert list(_only_engine_call(moe)["prompt_token_ids"]) == [5, 6, 8]


def test_left_padded_hf_default_position_ids_accepted():
    input_ids = torch.tensor([[0, 0, 7, 8]], dtype=torch.long)
    mask = torch.tensor([[0, 0, 1, 1]], dtype=torch.long)
    hf_default = torch.tensor([[0, 0, 0, 1]], dtype=torch.long)
    moe = _make_moe()

    _generate(moe, input_ids, attention_mask=mask, position_ids=hf_default)

    assert list(_only_engine_call(moe)["prompt_token_ids"]) == [7, 8]

    moe2 = _make_moe()
    full = torch.arange(4, dtype=torch.long).unsqueeze(0)
    with pytest.raises(
        ValueError, match="position_ids is not supported on the native"
    ):
        _generate(moe2, input_ids, attention_mask=mask, position_ids=full)


# --- position_ids shape -------------------------------------------------------


@pytest.mark.parametrize(
    "position_ids",
    [
        torch.tensor([[0, 1, 2]], dtype=torch.long),
        torch.tensor([0, 1, 2, 3], dtype=torch.long),
    ],
    ids=["short", "1d"],
)
def test_position_ids_shape_mismatch_raises(position_ids):
    moe = _make_moe()
    with pytest.raises(ValueError, match="position_ids shape"):
        _generate(moe, _input_ids(), position_ids=position_ids)


# --- check order: attention_mask before position_ids --------------------------


def test_attention_mask_checked_before_position_ids():
    bad_pos = torch.tensor([[10, 11, 12, 13]], dtype=torch.long)

    moe = _make_moe()
    with pytest.raises(ValueError, match="attention_mask shape"):
        _generate(
            moe,
            _input_ids(),
            attention_mask=torch.ones((1, 3), dtype=torch.long),
            position_ids=bad_pos,
        )

    moe2 = _make_moe()
    with pytest.raises(ValueError, match="entire prompt"):
        _generate(
            moe2,
            _input_ids(),
            attention_mask=torch.zeros((1, 4), dtype=torch.long),
            position_ids=torch.tensor([[0, 1, 2]], dtype=torch.long),
        )


# --- HF-path control ----------------------------------------------------------


def test_hf_path_forwards_attention_mask_and_position_ids():
    moe = _make_moe(use_native_engine=False)
    mask = torch.tensor([[1, 1, 0, 1]], dtype=torch.long)
    position_ids = torch.tensor([[10, 11, 12, 13]], dtype=torch.long)

    _generate(moe, _input_ids(), attention_mask=mask, position_ids=position_ids)

    assert len(moe.model.calls) == 1
    ids, kwargs = moe.model.calls[0]
    assert ids.tolist() == [INPUT_ROW]
    assert "attention_mask" in kwargs and "position_ids" in kwargs
    assert torch.equal(kwargs["attention_mask"], mask)
    assert torch.equal(kwargs["position_ids"], position_ids)


# --- no mask / position kwargs == stock behaviour ------------------------------


def test_no_mask_or_position_kwargs_uses_full_prompt():
    moe = _make_moe()

    out = _generate(moe, _input_ids())

    call = _only_engine_call(moe)
    assert set(call.keys()) == {"prompt_token_ids", "sampling_params"}
    assert list(call["prompt_token_ids"]) == INPUT_ROW
    assert call["sampling_params"] == SamplingParams(
        temperature=1.0, top_p=1.0, top_k=0, max_tokens=2
    )
    assert out.dtype == torch.long
    assert out.tolist() == [INPUT_ROW + ENGINE_OUTPUT]


# --- attention_mask must be 0/1 valued ----------------------------------------


@pytest.mark.parametrize(
    "mask",
    [
        torch.tensor([[2, -1, 0, 1]], dtype=torch.long),
        torch.tensor([[0.5, 1.0, 0.0, 1.0]], dtype=torch.float32),
        torch.tensor([[1, 1, 2, 1]], dtype=torch.long),
    ],
    ids=["int-2-neg1", "float-half", "int-single-2"],
)
def test_non_binary_attention_mask_raises(mask):
    moe = _make_moe()
    with pytest.raises(ValueError, match="must be 0/1 valued"):
        _generate(moe, _input_ids(), attention_mask=mask)


@pytest.mark.parametrize(
    "mask",
    [
        torch.tensor([[True, True, False, True]]),
        torch.tensor([[1.0, 1.0, 0.0, 1.0]], dtype=torch.float32),
    ],
    ids=["bool", "float-binary"],
)
def test_binary_non_long_attention_mask_accepted(mask):
    moe = _make_moe()
    out = _generate(moe, _input_ids(), attention_mask=mask)
    assert list(_only_engine_call(moe)["prompt_token_ids"]) == [5, 6, 8]
    assert out.tolist() == [INPUT_ROW + ENGINE_OUTPUT]


def test_non_binary_mask_checked_before_all_zero():
    # Truncated to int this mask is all-zero; the 0/1 check must run first
    # (shape -> 0/1-valued -> all-zero -> trim) and must not truncate.
    moe = _make_moe()
    mask = torch.tensor([[0.0, 0.0, 0.4, 0.0]], dtype=torch.float32)
    with pytest.raises(ValueError, match="must be 0/1 valued"):
        _generate(moe, _input_ids(), attention_mask=mask)


def test_mask_shape_checked_before_binary():
    moe = _make_moe()
    mask = torch.tensor([[2, 2, 2]], dtype=torch.long)
    with pytest.raises(ValueError, match="attention_mask shape"):
        _generate(moe, _input_ids(), attention_mask=mask)


# --- position_ids default check must not truncate ------------------------------


def test_fractional_float_position_ids_raise():
    moe = _make_moe()
    position_ids = torch.tensor([[0.0, 1.5, 2.9, 3.2]], dtype=torch.float32)
    with pytest.raises(
        ValueError, match="position_ids is not supported on the native"
    ):
        _generate(moe, _input_ids(), position_ids=position_ids)


def test_float_default_position_ids_accepted():
    moe = _make_moe()
    position_ids = torch.tensor([[0.0, 1.0, 2.0, 3.0]], dtype=torch.float32)

    out = _generate(moe, _input_ids(), position_ids=position_ids)

    call = _only_engine_call(moe)
    assert set(call.keys()) == {"prompt_token_ids", "sampling_params"}
    assert list(call["prompt_token_ids"]) == INPUT_ROW
    assert out.tolist() == [INPUT_ROW + ENGINE_OUTPUT]


# --- raise paths are side-effect free ------------------------------------------


@pytest.mark.parametrize(
    "kwargs, match",
    [
        (
            {"attention_mask": torch.ones((1, 3), dtype=torch.long)},
            "attention_mask shape",
        ),
        (
            {"attention_mask": torch.tensor([[2, -1, 0, 1]], dtype=torch.long)},
            "must be 0/1 valued",
        ),
        (
            {"attention_mask": torch.zeros((1, 4), dtype=torch.long)},
            "entire prompt",
        ),
        (
            {"position_ids": torch.tensor([[0, 1, 2]], dtype=torch.long)},
            "position_ids shape",
        ),
        (
            {
                "position_ids": torch.tensor(
                    [[10, 11, 12, 13]], dtype=torch.long
                )
            },
            "position_ids is not supported on the native",
        ),
        (
            {
                "position_ids": torch.tensor(
                    [[0.0, 1.5, 2.9, 3.2]], dtype=torch.float32
                )
            },
            "position_ids is not supported on the native",
        ),
    ],
    ids=[
        "mask-shape",
        "mask-non-binary",
        "mask-all-zero",
        "pos-shape",
        "pos-non-default",
        "pos-float-non-default",
    ],
)
def test_raise_paths_have_no_side_effects(kwargs, match):
    moe = _make_moe()
    with pytest.raises(ValueError, match=match):
        _generate(moe, _input_ids(), **kwargs)
    assert moe._configure_hook.call_count == 0
    assert moe._native_generation_engine.calls == []
