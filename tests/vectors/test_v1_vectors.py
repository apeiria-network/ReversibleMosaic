from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from reversible_mosaic.core.algorithm.reference_v1 import decrypt, encrypt


def test_draft_fixed_vectors() -> None:
    path = Path(__file__).with_name("algorithm_v1_draft.json")
    document = json.loads(path.read_text(encoding="ascii"))
    assert document["algorithm_version"] == 1
    assert document["status"] == "draft"
    for vector in document["vectors"]:
        channels = 3 if vector["mode"] == "RGB" else 4
        source = np.frombuffer(bytes.fromhex(vector["input_hex"]), dtype=np.uint8).reshape(
            vector["height"], vector["width"], channels
        )
        expected = bytes.fromhex(vector["encrypted_hex"])
        encrypted = encrypt(source, vector["seed"], vector["rounds"])
        assert encrypted.tobytes() == expected
        np.testing.assert_array_equal(
            decrypt(encrypted, vector["seed"], vector["rounds"]), source
        )
