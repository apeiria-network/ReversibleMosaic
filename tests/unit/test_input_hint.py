"""Unit tests for :mod:`reversible_mosaic.ui.input_hint`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from reversible_mosaic.core.algorithm.reference_v1 import encrypt
from reversible_mosaic.io.normalize import write_png
from reversible_mosaic.io.png_metadata import MetadataStatus, MosaicMetadata
from reversible_mosaic.ui.input_hint import format_file_size, inspect_input


def test_inspect_input_missing_file(tmp_path: Path) -> None:
    hint = inspect_input(tmp_path / "does_not_exist.png")
    assert not hint.is_ok
    assert hint.error is not None
    assert "无法读取文件" in hint.error


def test_inspect_input_unsupported_extension(tmp_path: Path) -> None:
    file = tmp_path / "sample.gif"
    file.write_bytes(b"not really a gif")
    hint = inspect_input(file)
    assert not hint.is_ok
    assert hint.error is not None
    assert "不支持" in hint.error


def test_inspect_input_valid_png_without_metadata(tmp_path: Path) -> None:
    pixels = np.zeros((16, 24, 3), dtype=np.uint8)
    pixels[..., 0] = 200
    file = tmp_path / "plain.png"
    Image.fromarray(pixels, "RGB").save(file, format="PNG")
    hint = inspect_input(file)
    assert hint.is_ok
    assert hint.format == "PNG"
    assert hint.width == 24
    assert hint.height == 16
    assert hint.mode == "RGB"
    assert hint.metadata.status is MetadataStatus.ABSENT
    assert hint.suggested_rounds is None
    assert hint.suggested_algorithm_version is None


def test_inspect_input_encrypted_png_metadata(tmp_path: Path) -> None:
    pixels = np.arange(16 * 24 * 3, dtype=np.uint8).reshape(16, 24, 3)
    encrypted = encrypt(pixels, seed=500000, rounds=5)
    metadata = MosaicMetadata(
        schema_version=1,
        app_marker="reversible_mosaic",
        operation_type="encrypted",
        algorithm_version=1,
        rounds=5,
        pixel_mode="RGB",
        width=24,
        height=16,
    )
    file = tmp_path / "encoded.png"
    write_png(file, encrypted, metadata)
    hint = inspect_input(file)
    assert hint.is_ok
    assert hint.has_encrypted_metadata
    assert hint.suggested_rounds == 5
    assert hint.suggested_algorithm_version == 1


def test_inspect_input_jpeg(tmp_path: Path) -> None:
    pixels = np.zeros((10, 12, 3), dtype=np.uint8)
    pixels[..., 1] = 128
    file = tmp_path / "photo.jpg"
    Image.fromarray(pixels, "RGB").save(file, format="JPEG")
    hint = inspect_input(file)
    assert hint.is_ok
    assert hint.format == "JPEG"
    assert hint.width == 12
    assert hint.height == 10
    assert hint.mode == "RGB"


def test_format_file_size_units() -> None:
    assert format_file_size(0) == "0 B"
    assert format_file_size(512) == "512 B"
    assert format_file_size(2048).endswith("KB")
    assert format_file_size(2 * 1024 * 1024).endswith("MB")


def test_inspect_input_invalid_png(tmp_path: Path) -> None:
    file = tmp_path / "broken.png"
    file.write_bytes(b"\x89PNG\r\n\x1a\nfake truncated")
    hint = inspect_input(file)
    assert not hint.is_ok
    assert hint.format == "PNG"


@pytest.mark.parametrize("bytes_count,expected_units", [
    (100, "B"),
    (5000, "KB"),
    (5_000_000, "MB"),
])
def test_format_file_size_ranges(bytes_count: int, expected_units: str) -> None:
    assert format_file_size(bytes_count).endswith(expected_units)


def test_inspect_input_sniffs_by_content_not_extension(tmp_path: Path) -> None:
    """A JPEG stream saved under a .png filename must still be recognised."""
    pixels = np.zeros((8, 8, 3), dtype=np.uint8)
    pixels[..., 2] = 200
    disguised = tmp_path / "screenshot.png"
    Image.fromarray(pixels, "RGB").save(disguised, format="JPEG")
    hint = inspect_input(disguised)
    assert hint.is_ok
    assert hint.format == "JPEG"
    assert hint.width == 8
    assert hint.height == 8
    assert hint.mode == "RGB"


def test_inspect_input_rejects_random_binary(tmp_path: Path) -> None:
    file = tmp_path / "opaque.bin"
    file.write_bytes(b"\x00\x01\x02" * 100)
    hint = inspect_input(file)
    assert not hint.is_ok
    assert "PNG 或 JPEG" in (hint.error or "")
