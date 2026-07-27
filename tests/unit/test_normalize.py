from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from reversible_mosaic.io.normalize import normalize_image, write_png
from reversible_mosaic.io.png_metadata import MosaicMetadata, parse_png_metadata
from reversible_mosaic.io.probe import scan_png


def metadata(mode: str, width: int, height: int) -> MosaicMetadata:
    return MosaicMetadata(  # type: ignore[arg-type]
        1, "reversible_mosaic", "encrypted", 1, 5, mode, width, height
    )


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
