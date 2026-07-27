"""Adversarial / malformed input tests."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, PngImagePlugin

from reversible_mosaic.io.normalize import normalize_image
from reversible_mosaic.io.png_metadata import (
    MAX_TOTAL_TEXT_BYTES,
    METADATA_KEYWORD,
    MetadataStatus,
    parse_png_metadata,
)
from reversible_mosaic.io.probe import ImageProbeError, scan_png


def _crc_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(
        ">I", zlib.crc32(kind + data) & 0xFFFFFFFF
    )


def _make_ihdr(width: int, height: int, color_type: int = 2) -> bytes:
    return struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)


def _base_png(width: int = 4, height: int = 4) -> bytes:
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(width, height))
    raw = b""
    for _ in range(height):
        raw += b"\x00" + b"\x00" * (width * 3)
    idat = _crc_chunk(b"IDAT", zlib.compress(raw))
    iend = _crc_chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def test_animated_png_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "animated.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(2, 2))
    actl = _crc_chunk(b"acTL", struct.pack(">II", 1, 0))
    iend = _crc_chunk(b"IEND", b"")
    idat = _crc_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00\x00\x00\x00"))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + actl + idat + iend)
    with pytest.raises(ImageProbeError, match="动画"):
        scan_png(path)


def test_png_over_max_edge_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "huge.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(10000, 10000))
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + iend)
    with pytest.raises(ImageProbeError):
        scan_png(path)


def test_png_with_extreme_aspect_ratio_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "narrow.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(8000, 4))  # 2000:1 aspect
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + iend)
    with pytest.raises(ImageProbeError):
        scan_png(path)


def test_png_text_metadata_over_64kib_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "textbomb.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(1, 1))
    filler = _crc_chunk(b"tEXt", b"noise\x00" + b"A" * (MAX_TOTAL_TEXT_BYTES + 128))
    idat = _crc_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + filler + idat + iend)
    with pytest.raises(ImageProbeError, match="文本"):
        scan_png(path)


def test_png_with_extra_bytes_after_iend_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "trailing.png"
    path.write_bytes(_base_png() + b"trailing garbage")
    with pytest.raises(ImageProbeError):
        scan_png(path)


def test_duplicate_metadata_chunks_are_flagged_invalid() -> None:
    duplicate = [
        (b"tEXt", METADATA_KEYWORD + b"\x00" + b'{"schema_version":1}'),
        (b"tEXt", METADATA_KEYWORD + b"\x00" + b'{"schema_version":1}'),
    ]
    result = parse_png_metadata(duplicate)
    assert result.status == MetadataStatus.INVALID


def test_metadata_with_conflicting_dimensions_is_flagged_conflict() -> None:
    from reversible_mosaic.io.png_metadata import MosaicMetadata, serialize_metadata

    metadata = MosaicMetadata(1, "reversible_mosaic", "encrypted", 1, 5, "RGB", 32, 32)
    chunk = (b"tEXt", METADATA_KEYWORD + b"\x00" + serialize_metadata(metadata).encode("ascii"))
    result = parse_png_metadata([chunk], actual_mode="RGB", actual_size=(16, 16))
    assert result.status == MetadataStatus.CONFLICT


def test_unknown_fields_are_ignored_but_required_fields_enforced() -> None:
    payload = (
        b'{"schema_version":1,"app_marker":"reversible_mosaic","operation_type":"encrypted",'
        b'"algorithm_version":1,"rounds":5,"pixel_mode":"RGB","width":8,"height":8,"future":"x"}'
    )
    chunk = (b"tEXt", METADATA_KEYWORD + b"\x00" + payload)
    result = parse_png_metadata([chunk])
    assert result.status == MetadataStatus.VALID
    assert result.metadata is not None
    assert result.metadata.width == 8


def test_metadata_rejects_nested_json() -> None:
    payload = b'{"schema_version":1,"nested":{"a":1}}'
    chunk = (b"tEXt", METADATA_KEYWORD + b"\x00" + payload)
    result = parse_png_metadata([chunk])
    assert result.status == MetadataStatus.INVALID


def test_bogus_signature_bytes_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "spoof.png"
    path.write_bytes(b"\x89PNG" + b"\x00" * 4 + _base_png()[8:])
    with pytest.raises(ImageProbeError):
        scan_png(path)


def test_png_missing_ihdr_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "no_ihdr.png"
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + iend)
    with pytest.raises(ImageProbeError):
        scan_png(path)


def test_valid_probe_png_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "good.png"
    pixels = np.arange(4 * 4 * 3, dtype=np.uint8).reshape(4, 4, 3)
    info = PngImagePlugin.PngInfo()
    Image.fromarray(pixels, mode="RGB").save(path, pnginfo=info)
    normalized = normalize_image(path)
    assert normalized.mode == "RGB"
    assert (normalized.width, normalized.height) == (4, 4)
    np.testing.assert_array_equal(normalized.pixels, pixels)
