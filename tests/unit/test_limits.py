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
    [
        (1, 1),
        (12288, 192),  # exactly 64:1 aspect at max edge
        (64, 1),
        (4000, 3000),
        (4096, 3072),
        (5000, 4000),
        (6000, 4000),  # 24MP 3:2 phone camera direct output
        (5657, 4243),  # 24MP 4:3
        (9798, 2449),  # 24MP 4:1 mild panorama
        (8000, 6000),  # 48MP 4:3 direct output (Xiaomi/Samsung common)
        (8160, 6120),  # 50MP 4:3 flagship main camera direct output
        (10000, 5000),  # 50M pixels at 2:1
    ],
)
def test_valid_dimensions(width: int, height: int) -> None:
    validate_dimensions(width, height)


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (0, 1),
        (1, 0),
        (12289, 1),  # 1 past MAX_EDGE
        (65, 1),  # aspect > 64:1
        (10001, 5000),  # 50M + 5000 pixels over MAX_PIXELS
        (12000, 9000),  # 108MP direct output — 108M pixels, over MAX_PIXELS
        (16000, 12000),  # 200MP direct output — both dims + total exceed
    ],
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
