"""Visual quality metrics used to gate V1 before release.

Requirements §12.3.3 lists three metrics that must be measured on the fixed
image set before the algorithm can be frozen:

- **Pixel change rate** — fraction of RGB channel values that changed between
  the source and the scrambled output. Higher is more scrambled.
- **Adjacent-pixel correlation** — Pearson correlation between neighbouring
  pixel luminance values along horizontal / vertical / diagonal directions.
  Values close to 0 indicate the local structure was destroyed.
- **Edge similarity** — Jaccard similarity between binarised Sobel edge maps
  of source and output. Lower means the visible edges no longer align with the
  original.

All functions accept HxWx3 or HxWx4 uint8 arrays; only the RGB channels
participate in the calculation (Alpha is ignored so transparency does not
skew the correlation).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from reversible_mosaic.core.algorithm.contracts import PixelArray

_RGB_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float64)
_SOBEL_X = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64)
_SOBEL_Y = _SOBEL_X.T


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    """Numeric summary of a single (source, scrambled) pair."""

    pixel_change_rate: float
    horizontal_correlation: float
    vertical_correlation: float
    diagonal_correlation: float
    edge_similarity: float

    def as_dict(self) -> dict[str, float]:
        return {
            "pixel_change_rate": self.pixel_change_rate,
            "horizontal_correlation": self.horizontal_correlation,
            "vertical_correlation": self.vertical_correlation,
            "diagonal_correlation": self.diagonal_correlation,
            "edge_similarity": self.edge_similarity,
        }


def _rgb(pixels: PixelArray) -> npt.NDArray[np.uint8]:
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
        raise ValueError("像素矩阵必须为 HxWx3 或 HxWx4。")
    return pixels[..., :3]


def _luminance(pixels: PixelArray) -> npt.NDArray[np.float64]:
    return _rgb(pixels).astype(np.float64) @ _RGB_LUMA


def pixel_change_rate(source: PixelArray, scrambled: PixelArray) -> float:
    """Fraction of RGB channel bytes that changed."""
    source_rgb = _rgb(source)
    scrambled_rgb = _rgb(scrambled)
    if source_rgb.shape != scrambled_rgb.shape:
        raise ValueError("原图与打码结果尺寸不一致。")
    if source_rgb.size == 0:
        return 0.0
    return float(np.mean(source_rgb != scrambled_rgb))


def _pearson(x: npt.NDArray[np.float64], y: npt.NDArray[np.float64]) -> float:
    if x.size < 2:
        return 0.0
    x_centered = x - x.mean()
    y_centered = y - y.mean()
    denom = float(np.sqrt(np.sum(x_centered**2) * np.sum(y_centered**2)))
    if denom == 0.0:
        return 0.0
    return float(np.sum(x_centered * y_centered) / denom)


def adjacent_pixel_correlations(pixels: PixelArray) -> tuple[float, float, float]:
    """Return (horizontal, vertical, diagonal) luminance correlations."""
    luminance = _luminance(pixels)
    height, width = luminance.shape
    if width < 2 or height < 2:
        # Fall back to whatever pair still exists.
        horizontal = (
            _pearson(luminance[:, :-1].ravel(), luminance[:, 1:].ravel())
            if width >= 2
            else 0.0
        )
        vertical = (
            _pearson(luminance[:-1, :].ravel(), luminance[1:, :].ravel())
            if height >= 2
            else 0.0
        )
        diagonal = (
            _pearson(luminance[:-1, :-1].ravel(), luminance[1:, 1:].ravel())
            if width >= 2 and height >= 2
            else 0.0
        )
        return horizontal, vertical, diagonal
    horizontal = _pearson(luminance[:, :-1].ravel(), luminance[:, 1:].ravel())
    vertical = _pearson(luminance[:-1, :].ravel(), luminance[1:, :].ravel())
    diagonal = _pearson(luminance[:-1, :-1].ravel(), luminance[1:, 1:].ravel())
    return horizontal, vertical, diagonal


def _convolve2d_valid(image: npt.NDArray[np.float64], kernel: npt.NDArray[np.float64]) -> (
    npt.NDArray[np.float64]
):
    kernel_h, kernel_w = kernel.shape
    output_h = image.shape[0] - kernel_h + 1
    output_w = image.shape[1] - kernel_w + 1
    result = np.zeros((output_h, output_w), dtype=np.float64)
    for row in range(kernel_h):
        for column in range(kernel_w):
            result += (
                kernel[row, column]
                * image[row : row + output_h, column : column + output_w]
            )
    return result


def _sobel_edges(pixels: PixelArray) -> npt.NDArray[np.bool_]:
    luminance = _luminance(pixels)
    if luminance.shape[0] < 3 or luminance.shape[1] < 3:
        return np.zeros_like(luminance, dtype=np.bool_)
    gx = _convolve2d_valid(luminance, _SOBEL_X)
    gy = _convolve2d_valid(luminance, _SOBEL_Y)
    magnitude = np.hypot(gx, gy)
    if magnitude.size == 0 or magnitude.max() == 0.0:
        return np.zeros_like(magnitude, dtype=np.bool_)
    # Threshold at the classical Sobel default: 50 (out of ~1443 max) then
    # clip against per-image mean so mostly-flat images do not report noise.
    threshold = max(50.0, float(magnitude.mean()))
    return magnitude >= threshold


def edge_similarity(source: PixelArray, scrambled: PixelArray) -> float:
    """Jaccard similarity between binarised Sobel edge maps."""
    source_edges = _sobel_edges(source)
    scrambled_edges = _sobel_edges(scrambled)
    if source_edges.shape != scrambled_edges.shape:
        raise ValueError("原图与打码结果尺寸不一致。")
    intersection = int(np.logical_and(source_edges, scrambled_edges).sum())
    union = int(np.logical_or(source_edges, scrambled_edges).sum())
    if union == 0:
        return 0.0
    return intersection / union


def compute_metrics(source: PixelArray, scrambled: PixelArray) -> QualityMetrics:
    """Compute all §12.3.3 metrics for one (source, scrambled) pair."""
    horizontal, vertical, diagonal = adjacent_pixel_correlations(scrambled)
    return QualityMetrics(
        pixel_change_rate=pixel_change_rate(source, scrambled),
        horizontal_correlation=horizontal,
        vertical_correlation=vertical,
        diagonal_correlation=diagonal,
        edge_similarity=edge_similarity(source, scrambled),
    )
