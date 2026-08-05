from __future__ import annotations

import codecs
import csv
import hashlib
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parents[2] / "scripts" / "generate_synthetic_test_set.py"
_SPEC = importlib.util.spec_from_file_location("generate_synthetic_test_set", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_GENERATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_GENERATOR)


def test_manifest_uses_bom_and_preserves_artifact_hashes(tmp_path: Path) -> None:
    artifact = tmp_path / "sample.png"
    artifact.write_bytes(b"synthetic image bytes")

    _GENERATOR._write_manifest(tmp_path, [(artifact.name, "中文说明")])

    manifest = tmp_path / "manifest.csv"
    assert manifest.read_bytes().startswith(codecs.BOM_UTF8)
    with manifest.open(encoding="utf-8-sig", newline="") as source:
        row = next(csv.DictReader(source))

    assert row["notes"] == "中文说明"
    assert row["license"] == "本项目 CC0"
    assert row["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
