from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from reversible_mosaic.core.pipeline import process_image
from reversible_mosaic.io.normalize import normalize_image
from reversible_mosaic.io.png_metadata import METADATA_KEYWORD


def test_encrypt_then_restore_without_metadata_dependency(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    encrypted_path = tmp_path / "encrypted.png"
    stripped_path = tmp_path / "stripped.png"
    restored_path = tmp_path / "restored.png"
    source = np.arange(5 * 7 * 4, dtype=np.uint8).reshape(5, 7, 4)
    source[:, :, 3] = np.arange(35, dtype=np.uint8).reshape(5, 7)
    Image.fromarray(source, mode="RGBA").save(source_path)

    encrypted = process_image(
        source_path,
        encrypted_path,
        operation="encrypted",
        rounds=5,
        share_code="000123",
    )
    assert encrypted.share_code.normalized == "123"
    assert b"123" not in encrypted_path.name.encode()
    assert METADATA_KEYWORD in encrypted_path.read_bytes()

    with Image.open(encrypted_path) as image:
        image.save(stripped_path, format="PNG")
    restored = process_image(
        stripped_path,
        restored_path,
        operation="restored",
        rounds=5,
        share_code="123",
        algorithm_version=1,
    )
    np.testing.assert_array_equal(restored.pixels, source)
    np.testing.assert_array_equal(normalize_image(restored_path).pixels, source)
    assert b'"operation_type":"restored"' in restored_path.read_bytes()
