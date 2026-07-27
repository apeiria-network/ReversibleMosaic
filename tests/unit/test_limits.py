from __future__ import annotations

import pytest

from reversible_mosaic.domain.limits import (
    MAX_INPUT_BYTES,
    ResourceLimitError,
    estimate_peak_memory,
    validate_available_memory,
    validate_dimensions,
)


def test_documented_input_limit_is_binary_50_mib() -> None:
    assert MAX_INPUT_BYTES == 52_428_800


@pytest.mark.parametrize(
    ("width", "height"),
    [(1, 1), (8192, 128), (64, 1), (4000, 3000)],
)
def test_valid_dimensions(width: int, height: int) -> None:
    validate_dimensions(width, height)


@pytest.mark.parametrize(
    ("width", "height"),
    [(0, 1), (1, 0), (8193, 1), (65, 1), (4001, 3000)],
)
def test_invalid_dimensions(width: int, height: int) -> None:
    with pytest.raises(ResourceLimitError):
        validate_dimensions(width, height)


def test_peak_memory_budget() -> None:
    estimate = estimate_peak_memory(1920, 1080, 4)
    assert estimate.pixel_bytes == 1920 * 1080 * 4
    validate_available_memory(estimate, estimate.peak_bytes * 2)
    with pytest.raises(ResourceLimitError):
        validate_available_memory(estimate, estimate.peak_bytes)
