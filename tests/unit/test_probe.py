from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from reversible_mosaic.io.probe import ImageProbeError, scan_png


def test_scan_valid_rgba_png_and_text(tmp_path: Path) -> None:
    path = tmp_path / "image.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("reversible_mosaic", "{}")
    Image.new("RGBA", (7, 9), (1, 2, 3, 0)).save(path, pnginfo=info)
    result = scan_png(path)
    assert (result.width, result.height, result.mode) == (7, 9, "RGBA")
    assert result.chunks[0][0] == b"tEXt"


def test_reject_non_png_and_bad_crc(tmp_path: Path) -> None:
    path = tmp_path / "bad.png"
    path.write_bytes(b"not png")
    with pytest.raises(ImageProbeError):
        scan_png(path)

    Image.new("RGB", (1, 1)).save(path)
    damaged = bytearray(path.read_bytes())
    damaged[29] ^= 1
    path.write_bytes(damaged)
    with pytest.raises(ImageProbeError, match="CRC"):
        scan_png(path)


def test_reject_unsupported_png_mode(tmp_path: Path) -> None:
    path = tmp_path / "gray.png"
    Image.new("L", (2, 2)).save(path)
    with pytest.raises(ImageProbeError, match="RGB/RGBA"):
        scan_png(path)
