from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from reversible_mosaic.core.algorithm.reference_v1 import decrypt, encrypt
from reversible_mosaic.core.algorithm.registry import get


def _load_vectors() -> dict:
    path = Path(__file__).with_name("algorithm_v1_draft.json")
    return json.loads(path.read_text(encoding="ascii"))


def test_draft_fixed_vectors() -> None:
    document = _load_vectors()
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


def test_registered_v1_matches_draft_fixed_vectors() -> None:
    """The currently-registered V1 backend (reference or Cython) must produce
    the same bytes as the frozen draft vectors."""

    document = _load_vectors()
    descriptor = get(1)
    for vector in document["vectors"]:
        channels = 3 if vector["mode"] == "RGB" else 4
        source = np.frombuffer(bytes.fromhex(vector["input_hex"]), dtype=np.uint8).reshape(
            vector["height"], vector["width"], channels
        )
        expected = bytes.fromhex(vector["encrypted_hex"])
        encrypted = descriptor.encrypt(source.copy(), vector["seed"], vector["rounds"], None)
        assert encrypted.tobytes() == expected
        restored = descriptor.decrypt(encrypted, vector["seed"], vector["rounds"], None)
        np.testing.assert_array_equal(restored, source)
