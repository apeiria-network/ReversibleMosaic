"""Adversarial / malformed input tests."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, PngImagePlugin

from reversible_mosaic.io.normalize import normalize_image, write_png
from reversible_mosaic.io.png_metadata import (
    MAX_TOTAL_TEXT_BYTES,
    MAX_VALUE_BYTES,
    METADATA_KEYWORD,
    MetadataStatus,
    MosaicMetadata,
    parse_png_metadata,
    serialize_metadata,
)
from reversible_mosaic.io.probe import MAX_CHUNK_BYTES, ImageProbeError, scan_png


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


# ---------------------------------------------------------------------------
# Block 1 fuzz — PNG chunk-level pathologies
# ---------------------------------------------------------------------------


def test_png_chunk_length_over_max_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "huge_chunk.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(4, 4))
    header = struct.pack(">I4s", MAX_CHUNK_BYTES + 1, b"IDAT")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + header)
    with pytest.raises(ImageProbeError, match="chunk"):
        scan_png(path)


def test_png_chunk_data_truncated_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "truncated.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(4, 4))
    header = struct.pack(">I4s", 100, b"IDAT") + b"only_a_few_bytes"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + header)
    with pytest.raises(ImageProbeError, match="chunk"):
        scan_png(path)


def test_png_chunk_bad_crc_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_crc.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(4, 4))
    idat_data = b"\x00" * 8
    corrupt = (
        struct.pack(">I", len(idat_data))
        + b"IDAT"
        + idat_data
        + struct.pack(">I", 0xDEADBEEF)
    )
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + corrupt + iend)
    with pytest.raises(ImageProbeError, match="CRC"):
        scan_png(path)


def test_png_ihdr_wrong_length_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "short_ihdr.png"
    short_ihdr = _crc_chunk(b"IHDR", b"\x00" * 12)  # 12 bytes, not 13
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + short_ihdr + iend)
    with pytest.raises(ImageProbeError, match="IHDR"):
        scan_png(path)


def test_png_ihdr_16bit_depth_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "depth16.png"
    ihdr_data = struct.pack(">IIBBBBB", 4, 4, 16, 2, 0, 0, 0)
    ihdr = _crc_chunk(b"IHDR", ihdr_data)
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + iend)
    with pytest.raises(ImageProbeError, match="8 位"):
        scan_png(path)


@pytest.mark.parametrize("color_type", [0, 3, 4])
def test_png_non_rgb_color_types_are_rejected(tmp_path: Path, color_type: int) -> None:
    path = tmp_path / f"color_{color_type}.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(4, 4, color_type=color_type))
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + iend)
    with pytest.raises(ImageProbeError, match="8 位"):
        scan_png(path)


def test_png_bad_compression_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_compression.png"
    ihdr_data = struct.pack(">IIBBBBB", 4, 4, 8, 2, 1, 0, 0)  # compression=1
    ihdr = _crc_chunk(b"IHDR", ihdr_data)
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + iend)
    with pytest.raises(ImageProbeError, match="编码参数"):
        scan_png(path)


def test_png_bad_filter_method_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_filter.png"
    ihdr_data = struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 1, 0)  # filter=1
    ihdr = _crc_chunk(b"IHDR", ihdr_data)
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + iend)
    with pytest.raises(ImageProbeError, match="编码参数"):
        scan_png(path)


def test_png_two_ihdr_chunks_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "double_ihdr.png"
    ihdr = _crc_chunk(b"IHDR", _make_ihdr(4, 4))
    iend = _crc_chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + ihdr + iend)
    with pytest.raises(ImageProbeError, match="IHDR"):
        scan_png(path)


def test_png_only_signature_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "just_signature.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ImageProbeError, match="截断"):
        scan_png(path)


def test_png_empty_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.png"
    path.write_bytes(b"")
    with pytest.raises(ImageProbeError):
        scan_png(path)


def test_png_over_50_mib_is_rejected(tmp_path: Path) -> None:
    # Only the size gate needs to trip; contents don't need to parse.
    path = tmp_path / "oversize.png"
    with path.open("wb") as fp:
        fp.write(b"\x89PNG\r\n\x1a\n")
        fp.truncate(60 * 1024 * 1024)
    with pytest.raises(ImageProbeError, match="50 MiB"):
        scan_png(path)


# ---------------------------------------------------------------------------
# Block 1 fuzz — metadata schema pathologies
# ---------------------------------------------------------------------------


def _payload(**overrides: object) -> bytes:
    fields: dict[str, object] = {
        "schema_version": 1,
        "app_marker": "reversible_mosaic",
        "operation_type": "encrypted",
        "algorithm_version": 1,
        "rounds": 5,
        "pixel_mode": "RGB",
        "width": 8,
        "height": 8,
    }
    fields.update(overrides)
    import json

    return json.dumps(fields, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _chunk(payload: bytes, *, kind: bytes = b"tEXt") -> tuple[bytes, bytes]:
    return (kind, METADATA_KEYWORD + b"\x00" + payload)


def test_metadata_via_ztxt_is_rejected() -> None:
    result = parse_png_metadata([_chunk(_payload(), kind=b"zTXt")])
    assert result.status == MetadataStatus.INVALID
    assert result.reason is not None and "tEXt" in result.reason


def test_metadata_via_itxt_is_rejected() -> None:
    result = parse_png_metadata([_chunk(_payload(), kind=b"iTXt")])
    assert result.status == MetadataStatus.INVALID


def test_metadata_value_over_2048_bytes_is_rejected() -> None:
    huge_marker = "reversible_mosaic" + "_" * (MAX_VALUE_BYTES + 32)
    result = parse_png_metadata([_chunk(_payload(app_marker=huge_marker))])
    assert result.status == MetadataStatus.INVALID


def test_metadata_non_ascii_value_is_rejected() -> None:
    payload = '{"schema_version":1,"app_marker":"reversible_mosaic","operation_type":"encrypted","algorithm_version":1,"rounds":5,"pixel_mode":"RGB","width":8,"height":8,"note":"你好"}'  # noqa: E501
    result = parse_png_metadata([(b"tEXt", METADATA_KEYWORD + b"\x00" + payload.encode("utf-8"))])
    assert result.status == MetadataStatus.INVALID


@pytest.mark.parametrize("schema", [0, 2, -1])
def test_metadata_unsupported_schema_is_rejected(schema: int) -> None:
    result = parse_png_metadata([_chunk(_payload(schema_version=schema))])
    assert result.status == MetadataStatus.INVALID


def test_metadata_wrong_app_marker_is_rejected() -> None:
    result = parse_png_metadata([_chunk(_payload(app_marker="something_else"))])
    assert result.status == MetadataStatus.INVALID


def test_metadata_unknown_operation_type_is_rejected() -> None:
    result = parse_png_metadata([_chunk(_payload(operation_type="mangled"))])
    assert result.status == MetadataStatus.INVALID


@pytest.mark.parametrize("version", [0, -1])
def test_metadata_non_positive_algorithm_version_is_rejected(version: int) -> None:
    result = parse_png_metadata([_chunk(_payload(algorithm_version=version))])
    assert result.status == MetadataStatus.INVALID


@pytest.mark.parametrize("rounds", [1, 3, 10, 20, 100])
def test_metadata_off_frozen_rounds_are_rejected(rounds: int) -> None:
    """Old round sets (1/10/20) and arbitrary numbers must be refused after §7.3
    was frozen to {2, 5, 15, 30}. rounds=10 in particular guards against
    accepting metadata written by pre-v14 builds."""
    result = parse_png_metadata([_chunk(_payload(rounds=rounds))])
    assert result.status == MetadataStatus.INVALID


def test_metadata_unknown_pixel_mode_is_rejected() -> None:
    result = parse_png_metadata([_chunk(_payload(pixel_mode="GRAY"))])
    assert result.status == MetadataStatus.INVALID


@pytest.mark.parametrize("dim_key", ["width", "height"])
def test_metadata_non_positive_dimensions_are_rejected(dim_key: str) -> None:
    result = parse_png_metadata([_chunk(_payload(**{dim_key: 0}))])
    assert result.status == MetadataStatus.INVALID


def test_metadata_missing_required_field_is_rejected() -> None:
    payload = (
        b'{"schema_version":1,"app_marker":"reversible_mosaic",'
        b'"operation_type":"encrypted","algorithm_version":1,"rounds":5,'
        b'"pixel_mode":"RGB","width":8}'  # missing height
    )
    result = parse_png_metadata([(b"tEXt", METADATA_KEYWORD + b"\x00" + payload)])
    assert result.status == MetadataStatus.INVALID


def test_metadata_string_instead_of_int_is_rejected() -> None:
    payload = (
        b'{"schema_version":1,"app_marker":"reversible_mosaic",'
        b'"operation_type":"encrypted","algorithm_version":"1","rounds":5,'
        b'"pixel_mode":"RGB","width":8,"height":8}'
    )
    result = parse_png_metadata([(b"tEXt", METADATA_KEYWORD + b"\x00" + payload)])
    assert result.status == MetadataStatus.INVALID


def test_metadata_bool_for_int_field_is_rejected() -> None:
    """Python's ``bool`` is a subclass of ``int``. The strict validator uses
    ``type() is not int`` precisely so ``True``/``False`` can't sneak in
    where an integer is required."""
    payload = (
        b'{"schema_version":1,"app_marker":"reversible_mosaic",'
        b'"operation_type":"encrypted","algorithm_version":true,"rounds":5,'
        b'"pixel_mode":"RGB","width":8,"height":8}'
    )
    result = parse_png_metadata([(b"tEXt", METADATA_KEYWORD + b"\x00" + payload)])
    assert result.status == MetadataStatus.INVALID


def test_metadata_four_candidates_is_flagged_invalid() -> None:
    # Duplicates within limit hit the "重复" branch, not the "超过" branch.
    result = parse_png_metadata([_chunk(_payload()) for _ in range(4)])
    assert result.status == MetadataStatus.INVALID
    assert result.reason is not None and "重复" in result.reason


def test_metadata_five_candidates_is_flagged_too_many() -> None:
    result = parse_png_metadata([_chunk(_payload()) for _ in range(5)])
    assert result.status == MetadataStatus.INVALID
    assert result.reason is not None and "过多" in result.reason


def test_metadata_no_null_separator_is_rejected() -> None:
    # Missing the mandatory \x00 between keyword and value.
    bad = METADATA_KEYWORD + b'{"schema_version":1}'
    result = parse_png_metadata([(b"tEXt", bad)])
    assert result.status == MetadataStatus.ABSENT
    # A tEXt chunk whose keyword doesn't equal ``reversible_mosaic`` because
    # the null separator was omitted is silently skipped -- no reversible_mosaic
    # metadata was present at all, which is ABSENT rather than INVALID.


def test_metadata_conflict_on_pixel_mode(tmp_path: Path) -> None:
    md = MosaicMetadata(1, "reversible_mosaic", "encrypted", 1, 5, "RGB", 4, 4)
    chunk = (b"tEXt", METADATA_KEYWORD + b"\x00" + serialize_metadata(md).encode("ascii"))
    result = parse_png_metadata([chunk], actual_mode="RGBA", actual_size=(4, 4))
    assert result.status == MetadataStatus.CONFLICT


def test_metadata_serialize_parse_round_trip() -> None:
    md = MosaicMetadata(1, "reversible_mosaic", "restored", 1, 30, "RGBA", 12, 34)
    encoded = serialize_metadata(md).encode("ascii")
    result = parse_png_metadata([(b"tEXt", METADATA_KEYWORD + b"\x00" + encoded)])
    assert result.status == MetadataStatus.VALID
    assert result.metadata == md


# ---------------------------------------------------------------------------
# Block 1 fuzz — JPEG pathologies
# ---------------------------------------------------------------------------


def test_jpeg_missing_soi_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "no_soi.jpg"
    # File that starts with something other than FFD8 gets kicked out by the
    # top-level signature check in normalize_image before preflight even runs.
    path.write_bytes(b"\x00\x00\x00\x00")
    with pytest.raises(ImageProbeError):
        normalize_image(path)


def test_jpeg_truncated_before_eoi_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "truncated.jpg"
    # SOI followed only by APP1 header — no EOI, no SOS.
    marker = b"\xff\xe1"
    length = struct.pack(">H", 20)
    payload = b"Exif\x00\x00" + b"\x00" * 12
    path.write_bytes(b"\xff\xd8" + marker + length + payload)
    with pytest.raises(ImageProbeError, match="JPEG"):
        normalize_image(path)


def test_jpeg_oversized_app1_segment_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "big_app1.jpg"
    marker = b"\xff\xe1"
    # Declared segment length > 1 MiB triggers the preflight bail-out.
    huge_len = struct.pack(">H", 0xFFFF)  # 65535 bytes segment
    path.write_bytes(b"\xff\xd8" + marker + huge_len + b"\x00" * 200)
    # The 65535 byte declared length exceeds the 200-byte body; preflight
    # trips on truncation before it even considers the segment cap.
    with pytest.raises(ImageProbeError, match="JPEG"):
        normalize_image(path)


def test_jpeg_segment_length_below_two_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_len.jpg"
    marker = b"\xff\xe1"
    length = struct.pack(">H", 1)  # invalid; JPEG spec says >= 2
    path.write_bytes(b"\xff\xd8" + marker + length + b"\x00")
    with pytest.raises(ImageProbeError, match="JPEG segment"):
        normalize_image(path)


# ---------------------------------------------------------------------------
# Block 1 — write_png metadata round-trip
# ---------------------------------------------------------------------------


def test_write_png_serializes_metadata_that_parses_back(tmp_path: Path) -> None:
    path = tmp_path / "with_meta.png"
    pixels = np.arange(4 * 4 * 3, dtype=np.uint8).reshape(4, 4, 3)
    md = MosaicMetadata(1, "reversible_mosaic", "encrypted", 1, 15, "RGB", 4, 4)
    write_png(path, pixels, md)

    probe = scan_png(path)
    result = parse_png_metadata(
        list(probe.chunks), actual_mode=probe.mode, actual_size=(probe.width, probe.height)
    )
    assert result.status == MetadataStatus.VALID
    assert result.metadata == md
    # Pixels survive the write→scan_png→PIL round trip.
    normalized = normalize_image(path)
    np.testing.assert_array_equal(normalized.pixels, pixels)
