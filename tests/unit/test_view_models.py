"""Tests for the view-model helpers used by encode/decode/progress screens."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from reversible_mosaic.core.pipeline import PipelineResult
from reversible_mosaic.domain.share_code import ShareCode, ShareCodeError
from reversible_mosaic.io.normalize import NormalizedImage
from reversible_mosaic.ui.view_models import (
    DEFAULT_ROUNDS,
    VALID_ROUNDS,
    ProgressSnapshot,
    ResultSnapshot,
    TaskFormState,
)


def test_default_rounds_is_valid() -> None:
    assert DEFAULT_ROUNDS in VALID_ROUNDS


def test_empty_share_code_maps_to_default() -> None:
    form = TaskFormState(operation="encrypted", input_path=Path("in.png"))
    assert form.parsed_share_code() == "500000"


def test_invalid_share_code_raises() -> None:
    form = TaskFormState(
        operation="encrypted",
        input_path=Path("in.png"),
        share_code="abc123",
    )
    with pytest.raises(ShareCodeError):
        form.parsed_share_code()


def test_can_start_requires_input_and_valid_rounds() -> None:
    form = TaskFormState(operation="encrypted")
    assert form.can_start() is False
    form.input_path = Path("in.png")
    assert form.can_start() is True
    form.rounds = 7
    assert form.can_start() is False


def test_randomize_share_code_avoids_default() -> None:
    form = TaskFormState(operation="encrypted")
    for _ in range(50):
        form.randomize_share_code()
        assert form.share_code != "500000"
        assert form.share_code.isdecimal()


def test_progress_snapshot_labels_known_stages() -> None:
    snapshot = ProgressSnapshot.from_stage("transform", 0.42)
    assert snapshot.label == "算法处理"
    assert snapshot.fraction == pytest.approx(0.42)
    unknown = ProgressSnapshot.from_stage("mystery", None)
    assert unknown.label == "mystery"


def test_algorithm_version_defaults_none_and_is_mutable() -> None:
    form = TaskFormState(operation="restored", input_path=Path("in.png"))
    assert form.algorithm_version is None
    form.algorithm_version = 1
    assert form.algorithm_version == 1


def test_original_display_name_defaults_none() -> None:
    form = TaskFormState(operation="encrypted")
    assert form.original_display_name is None
    form.original_display_name = "photo.jpg"
    assert form.original_display_name == "photo.jpg"


def _fake_pipeline_result(output: Path) -> PipelineResult:
    pixels = np.zeros((2, 2, 3), dtype=np.uint8)
    source = NormalizedImage(pixels=pixels.copy(), input_format="PNG", input_bytes=0)
    return PipelineResult(
        output_path=output,
        pixels=pixels,
        source=source,
        algorithm_version=1,
        rounds=5,
        share_code=ShareCode(normalized="500000", seed=500000, used_default=True),
    )


def test_result_snapshot_defaults_are_unsaved(tmp_path: Path) -> None:
    output = tmp_path / "photo_mosaic.png"
    snapshot = ResultSnapshot.from_pipeline(
        _fake_pipeline_result(output),
        operation="encrypted",
        display_name="photo_mosaic.png",
    )
    assert snapshot.is_saved is False
    assert snapshot.saved_handle is None
    assert snapshot.save_error is None
    assert snapshot.display_name == "photo_mosaic.png"
    assert snapshot.operation == "encrypted"


def test_result_snapshot_transitions_to_saved(tmp_path: Path) -> None:
    output = tmp_path / "photo_mosaic.png"
    snapshot = ResultSnapshot.from_pipeline(
        _fake_pipeline_result(output), operation="encrypted"
    )
    snapshot.saved_handle = "content://media/external/images/media/42"
    assert snapshot.is_saved is True


def test_result_snapshot_falls_back_to_output_name(tmp_path: Path) -> None:
    output = tmp_path / "photo_mosaic.png"
    snapshot = ResultSnapshot.from_pipeline(
        _fake_pipeline_result(output), operation="restored"
    )
    assert snapshot.display_name == "photo_mosaic.png"
    assert snapshot.operation == "restored"
