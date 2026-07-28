"""Unit tests for :mod:`reversible_mosaic.core.algorithm.quality`."""

from __future__ import annotations

import numpy as np
import pytest

from reversible_mosaic.core.algorithm.quality import (
    QualityMetrics,
    adjacent_pixel_correlations,
    compute_metrics,
    edge_similarity,
    pixel_change_rate,
)
from reversible_mosaic.core.algorithm.reference_v1 import encrypt


def _gradient_image(height: int, width: int, channels: int = 3) -> np.ndarray:
    row_ramp = np.linspace(0, 250, height, dtype=np.float64).reshape(-1, 1)
    column_ramp = np.linspace(0, 250, width, dtype=np.float64).reshape(1, -1)
    plane = ((row_ramp + column_ramp) / 2.0).clip(0.0, 255.0).astype(np.uint8)
    return np.stack([plane] * channels, axis=-1)


def test_pixel_change_rate_identity_is_zero() -> None:
    image = _gradient_image(4, 4)
    assert pixel_change_rate(image, image) == 0.0


def test_pixel_change_rate_full_change_is_one() -> None:
    image = _gradient_image(4, 4)
    shifted = ((image.astype(np.int32) + 1) % 256).astype(np.uint8)
    assert pixel_change_rate(image, shifted) == 1.0


def test_adjacent_correlation_of_gradient_is_high() -> None:
    image = _gradient_image(16, 16)
    horizontal, vertical, diagonal = adjacent_pixel_correlations(image)
    assert horizontal > 0.95
    assert vertical > 0.95
    assert diagonal > 0.90


def test_adjacent_correlation_of_random_noise_is_low() -> None:
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    horizontal, vertical, diagonal = adjacent_pixel_correlations(noise)
    assert abs(horizontal) < 0.1
    assert abs(vertical) < 0.1
    assert abs(diagonal) < 0.1


def test_edge_similarity_of_identical_images_is_one() -> None:
    image = _gradient_image(16, 16)
    assert edge_similarity(image, image) == pytest.approx(1.0)


def test_edge_similarity_of_flat_images_is_zero() -> None:
    flat = np.full((16, 16, 3), 128, dtype=np.uint8)
    other = flat.copy()
    other[..., 0] = 129
    assert edge_similarity(flat, other) == 0.0


def test_compute_metrics_on_scrambled_v1_output() -> None:
    image = _gradient_image(32, 32)
    scrambled = encrypt(image, 500_000, 5)
    metrics = compute_metrics(image, scrambled)
    assert isinstance(metrics, QualityMetrics)
    # 5 rounds should already change nearly every RGB byte.
    assert metrics.pixel_change_rate > 0.9
    # Adjacent correlations of the scrambled image should be near zero.
    assert abs(metrics.horizontal_correlation) < 0.2
    assert abs(metrics.vertical_correlation) < 0.2
    # Edges should not align with the source.
    assert metrics.edge_similarity < 0.2


def test_compute_metrics_ignores_alpha_channel() -> None:
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[..., :3] = _gradient_image(8, 8, 3)
    image[..., 3] = 255
    scrambled = encrypt(image, 500_000, 5)
    metrics = compute_metrics(image, scrambled)
    assert metrics.pixel_change_rate > 0.9


def test_compute_metrics_rejects_non_rgb() -> None:
    with pytest.raises(ValueError):
        compute_metrics(
            np.zeros((4, 4, 2), dtype=np.uint8),
            np.zeros((4, 4, 2), dtype=np.uint8),
        )


def test_compute_metrics_as_dict_keys() -> None:
    image = _gradient_image(8, 8)
    scrambled = encrypt(image, 500_000, 1)
    metrics = compute_metrics(image, scrambled)
    assert set(metrics.as_dict().keys()) == {
        "pixel_change_rate",
        "horizontal_correlation",
        "vertical_correlation",
        "diagonal_correlation",
        "edge_similarity",
    }
