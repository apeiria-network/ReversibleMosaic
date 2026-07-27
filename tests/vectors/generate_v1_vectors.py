"""Generate deterministic fixed vectors for an algorithm release candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from reversible_mosaic.core.algorithm.reference_v1 import decrypt, encrypt

_CASES = (
    ("rgb_1x1_r1_seed0", 1, 1, 3, 0, 1),
    ("rgba_3x2_r5_seed500000", 3, 2, 4, 500000, 5),
    ("rgb_5x3_r10_seed9999999999", 5, 3, 3, 9_999_999_999, 10),
    ("rgba_1x7_r20_seed123", 1, 7, 4, 123, 20),
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_vectors() -> dict[str, object]:
    vectors: list[dict[str, object]] = []
    for name, width, height, channels, seed, rounds in _CASES:
        source = np.arange(width * height * channels, dtype=np.uint8).reshape(
            height, width, channels
        )
        if channels == 4:
            source[:, :, 3] = np.arange(width * height, dtype=np.uint8).reshape(height, width)
        encrypted = encrypt(source, seed, rounds)
        restored = decrypt(encrypted, seed, rounds)
        if not np.array_equal(restored, source):
            raise RuntimeError(f"固定向量 {name} 无法恢复。")
        vectors.append(
            {
                "name": name,
                "width": width,
                "height": height,
                "mode": "RGB" if channels == 3 else "RGBA",
                "seed": seed,
                "rounds": rounds,
                "input_hex": source.tobytes().hex(),
                "encrypted_hex": encrypted.tobytes().hex(),
                "input_sha256": _digest(source.tobytes()),
                "encrypted_sha256": _digest(encrypted.tobytes()),
            }
        )
    return {"algorithm_version": 1, "status": "draft", "vectors": vectors}


def main() -> None:
    destination = Path(__file__).with_name("algorithm_v1_draft.json")
    destination.write_text(
        json.dumps(generate_vectors(), indent=2, ensure_ascii=True) + "\n", encoding="ascii"
    )


if __name__ == "__main__":
    main()
