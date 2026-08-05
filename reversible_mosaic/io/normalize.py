"""Safe normalization and lossless PNG writing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, PngImagePlugin

from reversible_mosaic.core.algorithm.contracts import PixelArray
from reversible_mosaic.domain.limits import (
    MAX_INPUT_BYTES,
    MAX_SEGMENT_BYTES,
    ResourceLimitError,
    validate_dimensions,
)
from reversible_mosaic.io.png_metadata import (
    METADATA_KEYWORD,
    MosaicMetadata,
    serialize_metadata,
)
from reversible_mosaic.io.probe import ImageProbeError, scan_png


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    pixels: PixelArray
    input_format: str
    input_bytes: int

    @property
    def mode(self) -> str:
        return "RGBA" if self.pixels.shape[2] == 4 else "RGB"

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])


_EXIF_ORIENTATION_TAG = 0x0112
_VALID_EXIF_ORIENTATIONS = frozenset(range(1, 9))


def _validate_exif_orientation(image: Image.Image) -> None:
    """Reject JPEGs whose EXIF Orientation is outside the 1-8 spec range.

    Requirements §7.2.4 fixes the accepted range and §10.3 mandates a
    controlled error for anomalous EXIF. Pillow's ``ImageOps.exif_transpose``
    silently falls back to identity for unknown values, so we have to check
    explicitly before invoking it.

    An Orientation of ``0`` is not in the EXIF 2.32 spec but is a common
    "no orientation info" convention emitted by several phone cameras and
    editors. We treat it as identity (equivalent to ``1``) — it doesn't
    enable any parser exploit, and rejecting it would kick out legitimate
    real-world photos. Anything else outside 1-8 is a hard error.
    """
    try:
        exif = image.getexif()
    except Exception:
        return
    if _EXIF_ORIENTATION_TAG not in exif:
        return
    orientation = exif[_EXIF_ORIENTATION_TAG]
    if orientation == 0:
        return
    if not isinstance(orientation, int) or orientation not in _VALID_EXIF_ORIENTATIONS:
        raise ImageProbeError(
            f"EXIF Orientation 取值不合规 ({orientation!r}), 必须为 1-8。"
        )


def _preflight_jpeg(source: Path) -> None:
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ImageProbeError("输入文件超过 50 MiB。")
    with source.open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            raise ImageProbeError("文件不是有效 JPEG。")
        while True:
            prefix = stream.read(1)
            if not prefix:
                raise ImageProbeError("JPEG 被截断。")
            if prefix != b"\xff":
                continue
            marker = stream.read(1)
            while marker == b"\xff":
                marker = stream.read(1)
            if not marker:
                raise ImageProbeError("JPEG 被截断。")
            code = marker[0]
            if code in (0xD8, 0xD9) or 0xD0 <= code <= 0xD7:
                if code == 0xD9:
                    return
                continue
            if code == 0xDA:
                return
            raw_length = stream.read(2)
            if len(raw_length) != 2:
                raise ImageProbeError("JPEG segment 被截断。")
            length = int.from_bytes(raw_length, "big")
            if length < 2 or length - 2 > MAX_SEGMENT_BYTES:
                raise ImageProbeError("JPEG segment 长度超限。")
            if len(stream.read(length - 2)) != length - 2:
                raise ImageProbeError("JPEG segment 被截断。")


def normalize_image(path: str | Path) -> NormalizedImage:
    """Decode a P0 image into an unpremultiplied, contiguous matrix."""
    source = Path(path)
    with source.open("rb") as stream:
        signature = stream.read(16)
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        probe = scan_png(source)
        expected_format = "PNG"
        expected_mode = probe.mode
    elif signature.startswith(b"\xff\xd8"):
        _preflight_jpeg(source)
        expected_format = "JPEG"
        expected_mode = "RGB"
    else:
        raise ImageProbeError("仅支持 PNG 或 JPEG。")

    try:
        with Image.open(source) as opened:
            # MPO (Multi-Picture Object) is a JPEG-based container used by many
            # phone cameras (iPhone Portrait mode, dual-lens Android) to bundle
            # depth / stereo frames with the primary JPEG. The primary frame is
            # a fully compliant JPEG, so we accept MPO wherever JPEG is allowed.
            observed_format = opened.format
            format_matches = observed_format == expected_format or (
                expected_format == "JPEG" and observed_format == "MPO"
            )
            if not format_matches:
                raise ImageProbeError("图片签名与解码格式不一致。")
            try:
                validate_dimensions(opened.width, opened.height)
            except ResourceLimitError as exc:
                raise ImageProbeError(str(exc)) from exc
            image = opened.copy()
            if image.format is None:
                image.format = observed_format
            if expected_format == "JPEG":
                if image.mode not in ("RGB", "L"):
                    raise ImageProbeError("仅支持普通 RGB JPEG。")
                _validate_exif_orientation(image)
                image = ImageOps.exif_transpose(image)
                if image.mode == "L":
                    raise ImageProbeError("灰度 JPEG 不属于 P0 支持范围。")
            if image.mode != expected_mode:
                raise ImageProbeError("图片像素模式不受支持。")
            pixels = np.asarray(image, dtype=np.uint8).copy(order="C")
    except ImageProbeError:
        raise
    except (OSError, ValueError) as exc:
        raise ImageProbeError("图片解码失败。") from exc

    return NormalizedImage(pixels, expected_format, source.stat().st_size)


def write_png(path: str | Path, pixels: PixelArray, metadata: MosaicMetadata) -> None:
    """Write one lossless PNG and verify its decoded pixels immediately."""
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4) or pixels.dtype != np.uint8:
        raise ValueError("输出像素必须是 uint8 RGB/RGBA。")
    mode = "RGB" if pixels.shape[2] == 3 else "RGBA"
    info = PngImagePlugin.PngInfo()
    info.add_text(METADATA_KEYWORD.decode("ascii"), serialize_metadata(metadata), zip=False)
    destination = Path(path)
    Image.fromarray(pixels, mode=mode).save(
        destination,
        format="PNG",
        pnginfo=info,
        optimize=True,
        compress_level=9,
    )
    probe = scan_png(destination)
    if (probe.width, probe.height, probe.mode) != (pixels.shape[1], pixels.shape[0], mode):
        destination.unlink(missing_ok=True)
        raise OSError("PNG 复读规格校验失败。")
    with Image.open(destination) as decoded:
        round_trip = np.asarray(decoded, dtype=np.uint8)
    if not np.array_equal(round_trip, pixels):
        destination.unlink(missing_ok=True)
        raise OSError("PNG 复读像素校验失败。")
