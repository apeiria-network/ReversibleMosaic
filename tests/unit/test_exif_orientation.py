"""EXIF Orientation 1-8 tests using synthesized JPEGs."""

from __future__ import annotations

import io
import struct
from pathlib import Path

import numpy as np
import piexif  # type: ignore[import-not-found]
import pytest
from PIL import Image

from reversible_mosaic.io.normalize import normalize_image
from reversible_mosaic.io.probe import ImageProbeError

BLOCK = 12
PALETTE = np.array(
    [
        [220, 40, 40],
        [40, 220, 40],
        [40, 40, 220],
        [220, 220, 40],
        [220, 40, 220],
        [40, 220, 220],
    ],
    dtype=np.uint8,
)


def _canonical_pixels() -> np.ndarray:
    canvas = np.zeros((2 * BLOCK, 3 * BLOCK, 3), dtype=np.uint8)
    for row in range(2):
        for col in range(3):
            canvas[row * BLOCK : (row + 1) * BLOCK, col * BLOCK : (col + 1) * BLOCK] = PALETTE[
                row * 3 + col
            ]
    return canvas


# Pillow's Image.transpose method that ImageOps.exif_transpose applies for
# each orientation tag. We store the encoded JPEG using the inverse transform
# so that decoding + exif_transpose reproduces the canonical layout.
_FORWARD_METHOD = {
    2: Image.FLIP_LEFT_RIGHT,
    3: Image.ROTATE_180,
    4: Image.FLIP_TOP_BOTTOM,
    5: Image.TRANSPOSE,
    6: Image.ROTATE_270,  # Pillow rotates 270 CCW; matches EXIF "rotate 90 CW"
    7: Image.TRANSVERSE,
    8: Image.ROTATE_90,
}
_INVERSE_METHOD = {
    2: Image.FLIP_LEFT_RIGHT,
    3: Image.ROTATE_180,
    4: Image.FLIP_TOP_BOTTOM,
    5: Image.TRANSPOSE,
    6: Image.ROTATE_90,
    7: Image.TRANSVERSE,
    8: Image.ROTATE_270,
}


def _encode_for_orientation(canonical: Image.Image, orientation: int) -> Image.Image:
    if orientation == 1:
        return canonical
    return canonical.transpose(_INVERSE_METHOD[orientation])


def _save_jpeg_with_orientation(path: Path, canonical: Image.Image, orientation: int) -> None:
    encoded = _encode_for_orientation(canonical, orientation)
    exif = {
        "0th": {piexif.ImageIFD.Orientation: orientation},
        "Exif": {},
        "1st": {},
        "thumbnail": None,
    }
    exif_bytes = piexif.dump(exif)
    buffer = io.BytesIO()
    encoded.save(buffer, format="JPEG", quality=100, subsampling=0, exif=exif_bytes)
    path.write_bytes(buffer.getvalue())


def _detect_palette(pixels: np.ndarray) -> np.ndarray:
    core = 4
    start = (BLOCK - core) // 2
    labels = np.zeros((2, 3), dtype=np.int32)
    palette_i = PALETTE.astype(np.int32)
    for row in range(2):
        for col in range(3):
            patch = pixels[
                row * BLOCK + start : row * BLOCK + start + core,
                col * BLOCK + start : col * BLOCK + start + core,
            ]
            mean = patch.mean(axis=(0, 1))
            distances = np.linalg.norm(palette_i - mean, axis=1)
            labels[row, col] = int(np.argmin(distances))
    return labels


@pytest.mark.parametrize("orientation", range(1, 9))
def test_exif_orientation_normalizes_to_canonical(tmp_path: Path, orientation: int) -> None:
    canonical = _canonical_pixels()
    canonical_image = Image.fromarray(canonical, mode="RGB")
    path = tmp_path / f"orient_{orientation}.jpg"
    _save_jpeg_with_orientation(path, canonical_image, orientation)

    normalized = normalize_image(path)

    assert (normalized.width, normalized.height, normalized.mode) == (
        canonical.shape[1],
        canonical.shape[0],
        "RGB",
    )
    labels = _detect_palette(normalized.pixels)
    expected_labels = np.arange(6, dtype=np.int32).reshape(2, 3)
    np.testing.assert_array_equal(labels, expected_labels)


def test_jpeg_with_truncated_marker_is_rejected(tmp_path: Path) -> None:
    truncated = tmp_path / "truncated.jpg"
    truncated.write_bytes(b"\xff\xd8\xff\xe1")
    with pytest.raises(ImageProbeError):
        normalize_image(truncated)


def test_jpeg_with_oversized_segment_is_rejected(tmp_path: Path) -> None:
    header = b"\xff\xd8"
    marker = b"\xff\xe1"
    body_length = 65535  # segment length field maximum
    payload = header + marker + struct.pack(">H", body_length) + b"A" * (body_length - 2)
    truncated = payload  # no SOS or EOI — must still parse-fail cleanly
    path = tmp_path / "oversized.jpg"
    path.write_bytes(truncated)
    with pytest.raises(ImageProbeError):
        normalize_image(path)

