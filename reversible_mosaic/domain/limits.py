"""Stable resource limits and preflight calculations."""

from __future__ import annotations

from dataclasses import dataclass

MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_EDGE = 8192
MAX_PIXELS = 12_000_000
MAX_ASPECT_RATIO = 64
MAX_SEGMENT_BYTES = 1024 * 1024
MAX_PNG_TEXT_BYTES = 64 * 1024
MAX_FULL_SIZE_BUFFERS = 3
MEMORY_FRACTION_LIMIT = 0.60


class ResourceLimitError(ValueError):
    """Raised before decoding when an input exceeds a stable P0 limit."""


@dataclass(frozen=True, slots=True)
class ResourceEstimate:
    pixel_bytes: int
    full_size_buffers: int
    fixed_overhead: int

    @property
    def peak_bytes(self) -> int:
        return self.pixel_bytes * self.full_size_buffers + self.fixed_overhead


def validate_dimensions(width: int, height: int) -> None:
    """Validate image dimensions without allocating the pixel matrix."""
    if width <= 0 or height <= 0:
        raise ResourceLimitError("图片宽高必须为正整数。")
    if width > MAX_EDGE or height > MAX_EDGE:
        raise ResourceLimitError(f"图片边长不能超过 {MAX_EDGE} 像素。")
    if width * height > MAX_PIXELS:
        raise ResourceLimitError(f"图片总像素不能超过 {MAX_PIXELS:,}。")
    if max(width, height) > min(width, height) * MAX_ASPECT_RATIO:
        raise ResourceLimitError(f"图片宽高比不能超过 {MAX_ASPECT_RATIO}:1。")


def estimate_peak_memory(
    width: int,
    height: int,
    channels: int,
    *,
    full_size_buffers: int = MAX_FULL_SIZE_BUFFERS,
    fixed_overhead: int = 64 * 1024 * 1024,
) -> ResourceEstimate:
    """Calculate a conservative peak-memory estimate."""
    validate_dimensions(width, height)
    if channels not in (3, 4):
        raise ResourceLimitError("仅支持 RGB 或 RGBA 像素。")
    if not 1 <= full_size_buffers <= MAX_FULL_SIZE_BUFFERS:
        raise ResourceLimitError("全尺寸缓冲区数量超出允许范围。")
    return ResourceEstimate(width * height * channels, full_size_buffers, fixed_overhead)


def validate_available_memory(estimate: ResourceEstimate, available_bytes: int) -> None:
    """Reject work predicted to use more than 60% of available app memory."""
    if available_bytes <= 0:
        raise ResourceLimitError("无法确定可用内存, 请稍后重试。")
    if estimate.peak_bytes > int(available_bytes * MEMORY_FRACTION_LIMIT):
        raise ResourceLimitError("预计内存占用过高, 请选择较小的图片。")
