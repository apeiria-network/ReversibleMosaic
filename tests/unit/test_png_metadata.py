from __future__ import annotations

import json

from reversible_mosaic.io.png_metadata import (
    METADATA_KEYWORD,
    MetadataStatus,
    MosaicMetadata,
    parse_png_metadata,
    serialize_metadata,
)


def sample_metadata() -> MosaicMetadata:
    return MosaicMetadata(1, "reversible_mosaic", "encrypted", 1, 5, "RGBA", 7, 9)


def text_chunk(metadata: MosaicMetadata | None = None) -> tuple[bytes, bytes]:
    value = serialize_metadata(metadata or sample_metadata()).encode("ascii")
    return b"tEXt", METADATA_KEYWORD + b"\x00" + value


def test_deterministic_round_trip() -> None:
    metadata = sample_metadata()
    encoded = serialize_metadata(metadata)
    assert "500000" not in encoded
    result = parse_png_metadata([text_chunk(metadata)], actual_mode="RGBA", actual_size=(7, 9))
    assert result.status is MetadataStatus.VALID
    assert result.metadata == metadata


def test_absent_and_duplicate() -> None:
    assert parse_png_metadata([]).status is MetadataStatus.ABSENT
    assert parse_png_metadata([text_chunk(), text_chunk()]).status is MetadataStatus.INVALID


def test_unknown_fields_are_ignored() -> None:
    raw = json.loads(serialize_metadata(sample_metadata()))
    raw["future"] = "ignored"
    chunk = (b"tEXt", METADATA_KEYWORD + b"\x00" + json.dumps(raw).encode("ascii"))
    assert parse_png_metadata([chunk]).status is MetadataStatus.VALID


def test_nested_and_wrong_types_are_invalid() -> None:
    raw = json.loads(serialize_metadata(sample_metadata()))
    raw["future"] = []
    nested = (b"tEXt", METADATA_KEYWORD + b"\x00" + json.dumps(raw).encode("ascii"))
    assert parse_png_metadata([nested]).status is MetadataStatus.INVALID
    raw.pop("future")
    raw["rounds"] = True
    wrong_type = (b"tEXt", METADATA_KEYWORD + b"\x00" + json.dumps(raw).encode("ascii"))
    assert parse_png_metadata([wrong_type]).status is MetadataStatus.INVALID


def test_compressed_protocol_and_conflicts_are_not_trusted() -> None:
    compressed = (b"zTXt", METADATA_KEYWORD + b"\x00\x00junk")
    assert parse_png_metadata([compressed]).status is MetadataStatus.INVALID
    result = parse_png_metadata([text_chunk()], actual_size=(8, 9))
    assert result.status is MetadataStatus.CONFLICT
    assert result.metadata == sample_metadata()


def test_total_text_and_value_limits() -> None:
    unrelated = (b"tEXt", b"other\x00" + b"x" * (64 * 1024))
    assert parse_png_metadata([unrelated, (b"tEXt", b"x")]).status is MetadataStatus.INVALID
    oversized = (b"tEXt", METADATA_KEYWORD + b"\x00" + b"x" * 2049)
    assert parse_png_metadata([oversized]).status is MetadataStatus.INVALID
