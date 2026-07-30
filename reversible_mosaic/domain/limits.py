"""Stable resource limits and preflight calculations."""

from __future__ import annotations

from dataclasses import dataclass

MAX_INPUT_BYTES = 50 * 1024 * 1024
# Bumped in v15 (2026-07-30) after v14's 30M cap still rejected mid-range
# 48-50MP direct outputs (8000x6000 = 48M, 8160x6120 ~= 50M). 4GB-only Android
# devices are essentially retired for the MVP target audience, so budgeting
# against 6-8GB mid-range is the new baseline. 50M pixels x 4 bytes x 3
# full-size buffers ~= 600MB + 64 MiB fixed overhead ~= 664 MiB peak -- fits
# in a 6-8GB device's native memory budget (Android system + Kivy + PIL
# together leave ~1-1.5GB usable). MAX_EDGE=12288 stays because 50MP 4:3
# direct output is only 8160 wide; only unrealistic >3:1 stitched 50MP
# panoramas would hit the edge cap first, and those are rare.
# Historic values: MAX_EDGE=8192 / MAX_PIXELS=20M (through v13);
# MAX_EDGE=12288 / MAX_PIXELS=30M (v14).
MAX_EDGE = 12288
MAX_PIXELS = 50_000_000
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
