"""Shared algorithm contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

PixelMode = Literal["RGB", "RGBA"]
PixelArray = npt.NDArray[np.uint8]
VALID_ROUNDS = frozenset({1, 5, 10, 20})


class AlgorithmError(ValueError):
    """Raised when an algorithm input violates the frozen contract."""


class CancellationRequested(RuntimeError):
    """Raised at a cooperative cancellation checkpoint."""


class CancellationProbe(Protocol):
    def __call__(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ImageSpec:
    width: int
    height: int
    mode: PixelMode

    @property
    def channels(self) -> int:
        return 3 if self.mode == "RGB" else 4


def validate_pixels(pixels: PixelArray, spec: ImageSpec) -> None:
    """Verify a matrix before any transformation occurs."""
    if pixels.dtype != np.uint8:
        raise AlgorithmError("像素数组必须使用 uint8。")
    if pixels.shape != (spec.height, spec.width, spec.channels):
        raise AlgorithmError("像素数组形状与图片规格不一致。")
    if not pixels.flags.c_contiguous:
        raise AlgorithmError("像素数组必须按行连续存储。")
