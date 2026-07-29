"""Cross-implementation byte-identity checks between reference and Cython V1.

Skipped on platforms where the Cython artefact was not built (e.g. Windows +
MSVC). On WSL / Linux CI the compiled ``v1`` extension must exist and both
implementations must produce identical bytes for every case.
"""

from __future__ import annotations

import numpy as np
import pytest

from reversible_mosaic.core.algorithm import reference_v1

try:
    from reversible_mosaic.core.algorithm import optimized_v1
except ImportError:  # pragma: no cover - PC branch without Cython artefact
    optimized_v1 = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    optimized_v1 is None,
    reason="Cython V1 module not built for this platform",
)


_CASES = (
    # (width, height, channels, seed, rounds)
    (1, 1, 3, 0, 1),
    (1, 1, 4, 500_000, 5),
    (3, 2, 3, 123, 10),
    (3, 2, 4, 500_000, 20),
    (5, 3, 3, 9_999_999_999, 10),
    (1, 7, 4, 1, 5),
    (7, 1, 3, 999_999, 20),
    (4, 4, 4, 0, 1),
)


def _make_source(width: int, height: int, channels: int) -> np.ndarray:
    source = np.arange(width * height * channels, dtype=np.uint8).reshape(
        height, width, channels
    )
    if channels == 4:
        source[:, :, 3] = np.arange(width * height, dtype=np.uint8).reshape(height, width)
    return source


@pytest.mark.parametrize(("width", "height", "channels", "seed", "rounds"), _CASES)
def test_optimized_matches_reference_encrypt(
    width: int, height: int, channels: int, seed: int, rounds: int
) -> None:
    source = _make_source(width, height, channels)
    expected = reference_v1.encrypt(source, seed, rounds)
    actual = optimized_v1.encrypt(source, seed, rounds)
    assert actual.tobytes() == expected.tobytes()


@pytest.mark.parametrize(("width", "height", "channels", "seed", "rounds"), _CASES)
def test_optimized_matches_reference_decrypt(
    width: int, height: int, channels: int, seed: int, rounds: int
) -> None:
    source = _make_source(width, height, channels)
    encrypted = reference_v1.encrypt(source, seed, rounds)
    expected = reference_v1.decrypt(encrypted, seed, rounds)
    actual = optimized_v1.decrypt(encrypted, seed, rounds)
    assert actual.tobytes() == expected.tobytes()
    np.testing.assert_array_equal(actual, source)


@pytest.mark.parametrize("rounds", [1, 5, 10, 20])
def test_optimized_roundtrip_rgba_with_transparent_pixels(rounds: int) -> None:
    height, width = 6, 5
    source = np.zeros((height, width, 4), dtype=np.uint8)
    source[..., 0] = np.arange(height * width, dtype=np.uint8).reshape(height, width)
    source[..., 1] = 200
    source[..., 2] = 50
    source[0, 0, 3] = 0
    source[1, 2, 3] = 0
    source[3, 4, 3] = 128
    source[5, 4, 3] = 255
    encrypted = optimized_v1.encrypt(source, 500_000, rounds)
    restored = optimized_v1.decrypt(encrypted, 500_000, rounds)
    np.testing.assert_array_equal(restored, source)
    np.testing.assert_array_equal(restored[..., 3], source[..., 3])


def test_registry_v1_backend_reports_cython_when_available() -> None:
    from reversible_mosaic.core.algorithm.registry import v1_implementation

    assert v1_implementation() == "cython"
