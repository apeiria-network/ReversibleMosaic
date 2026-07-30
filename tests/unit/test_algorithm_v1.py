from __future__ import annotations

import numpy as np
import pytest

from reversible_mosaic.core.algorithm.contracts import CancellationRequested
from reversible_mosaic.core.algorithm.reference_v1 import decrypt, encrypt


@pytest.mark.parametrize("channels", [3, 4])
@pytest.mark.parametrize("shape", [(1, 1), (1, 7), (5, 1), (5, 7)])
@pytest.mark.parametrize("rounds", [2, 5, 15, 30])
def test_round_trip(channels: int, shape: tuple[int, int], rounds: int) -> None:
    height, width = shape
    source = np.arange(height * width * channels, dtype=np.uint8).reshape(
        height, width, channels
    )
    encoded = encrypt(source, 500000, rounds)
    decoded = decrypt(encoded, 500000, rounds)
    np.testing.assert_array_equal(decoded, source)
    original = np.arange(source.size, dtype=np.uint8).reshape(source.shape)
    np.testing.assert_array_equal(source, original)


@pytest.mark.parametrize("rounds", [2, 5, 15, 30])
def test_rgba_alpha_values_only_move_with_pixels(rounds: int) -> None:
    source = np.zeros((3, 5, 4), dtype=np.uint8)
    source.reshape(-1, 4)[:, :3] = np.arange(45, dtype=np.uint8).reshape(-1, 3)
    source.reshape(-1, 4)[:, 3] = np.arange(15, dtype=np.uint8)
    encoded = encrypt(source, 123, rounds)
    assert sorted(encoded[:, :, 3].ravel()) == sorted(source[:, :, 3].ravel())
    np.testing.assert_array_equal(decrypt(encoded, 123, rounds), source)


def test_transparent_hidden_rgb_round_trip() -> None:
    source = np.array([[[11, 22, 33, 0], [44, 55, 66, 0]]], dtype=np.uint8)
    np.testing.assert_array_equal(decrypt(encrypt(source, 7, 5), 7, 5), source)


def test_deterministic_and_seed_sensitive() -> None:
    source = np.arange(9 * 11 * 3, dtype=np.uint8).reshape(9, 11, 3)
    first = encrypt(source, 123, 5)
    np.testing.assert_array_equal(first, encrypt(source, 123, 5))
    assert not np.array_equal(first, encrypt(source, 124, 5))


def test_cancel_before_first_round() -> None:
    source = np.zeros((1, 1, 3), dtype=np.uint8)
    with pytest.raises(CancellationRequested):
        encrypt(source, 1, 2, lambda: True)
