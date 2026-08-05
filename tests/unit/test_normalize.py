from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, PngImagePlugin

from reversible_mosaic.io.normalize import normalize_image, write_png
from reversible_mosaic.io.png_metadata import (
    METADATA_KEYWORD,
    MosaicMetadata,
    parse_png_metadata,
    serialize_metadata,
)
from reversible_mosaic.io.probe import scan_png


def metadata(mode: str, width: int, height: int) -> MosaicMetadata:
    return MosaicMetadata(  # type: ignore[arg-type]
        1, "reversible_mosaic", "encrypted", 1, 5, mode, width, height
    )


def test_rgb_png_round_trip_uses_lossless_optimized_encoding(tmp_path: Path) -> None:
    pixels = np.zeros((32, 32, 3), dtype=np.uint8)
    pixels[8:24, 8:24] = (11, 22, 33)
    path = tmp_path / "output.png"
    write_png(path, pixels, metadata("RGB", 32, 32))
    normalized = normalize_image(path)
    np.testing.assert_array_equal(normalized.pixels, pixels)
    probe = scan_png(path)
    parsed = parse_png_metadata(list(probe.chunks), actual_mode="RGB", actual_size=(32, 32))
    assert parsed.metadata == metadata("RGB", 32, 32)


def test_optimized_png_is_not_larger_than_pillow_default(tmp_path: Path) -> None:
    pixels = np.zeros((128, 128, 3), dtype=np.uint8)
    pixels[32:96, 32:96] = (11, 22, 33)
    optimized_path = tmp_path / "optimized.png"
    default_path = tmp_path / "default.png"
    write_png(optimized_path, pixels, metadata("RGB", 128, 128))
    default_info = PngImagePlugin.PngInfo()
    default_info.add_text(
        METADATA_KEYWORD.decode("ascii"),
        serialize_metadata(metadata("RGB", 128, 128)),
        zip=False,
    )
    Image.fromarray(pixels, mode="RGB").save(
        default_path,
        format="PNG",
        pnginfo=default_info,
    )
    assert optimized_path.stat().st_size <= default_path.stat().st_size


def test_rgba_hidden_rgb_png_round_trip(tmp_path: Path) -> None:
    pixels = np.array([[[11, 22, 33, 0], [44, 55, 66, 255]]], dtype=np.uint8)
    path = tmp_path / "output.png"
    write_png(path, pixels, metadata("RGBA", 2, 1))
    normalized = normalize_image(path)
    np.testing.assert_array_equal(normalized.pixels, pixels)
    probe = scan_png(path)
    parsed = parse_png_metadata(list(probe.chunks), actual_mode="RGBA", actual_size=(2, 1))
    assert parsed.metadata == metadata("RGBA", 2, 1)


def test_rgb_jpeg_normalizes_to_rgb(tmp_path: Path) -> None:
    path = tmp_path / "input.jpg"
    Image.new("RGB", (3, 2), (1, 2, 3)).save(path, quality=95)
    normalized = normalize_image(path)
    assert normalized.input_format == "JPEG"
    assert normalized.mode == "RGB"
    assert (normalized.width, normalized.height) == (3, 2)


def test_mpo_container_treated_as_jpeg(tmp_path: Path) -> None:
    """iPhone Portrait / dual-lens Android phones save primary photos as MPO
    (JPEG + auxiliary depth frames). The primary frame is a compliant JPEG,
    so the pipeline must accept ``opened.format == "MPO"`` alongside ``"JPEG"``.
    """
    path = tmp_path / "portrait.jpg"
    primary = Image.new("RGB", (3, 2), (10, 20, 30))
    aux = Image.new("RGB", (3, 2), (40, 50, 60))
    primary.save(path, format="MPO", quality=95, append_images=[aux], save_all=True)
    with Image.open(path) as opened:
        assert opened.format == "MPO"
    normalized = normalize_image(path)
    assert normalized.mode == "RGB"
    assert (normalized.width, normalized.height) == (3, 2)


def test_bogus_exif_orientation_is_rejected(tmp_path: Path) -> None:
    """Requirements §7.2.4 restrict Orientation to 1-8; anything else must
    raise a controlled error rather than silently fall back to identity."""
    import struct

    import pytest

    from reversible_mosaic.io.probe import ImageProbeError

    base = tmp_path / "base.jpg"
    Image.new("RGB", (8, 8), (200, 100, 50)).save(base, format="JPEG", quality=90)
    base_bytes = base.read_bytes()
    tiff = b"II*\x00" + struct.pack("<I", 8)
    tiff += struct.pack("<H", 1)
    tiff += struct.pack("<HHII", 0x0112, 3, 1, 42)
    tiff += struct.pack("<I", 0)
    exif_payload = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload
    injected = tmp_path / "bogus_exif.jpg"
    injected.write_bytes(base_bytes[:2] + app1 + base_bytes[2:])
    with pytest.raises(ImageProbeError, match="Orientation"):
        normalize_image(injected)
