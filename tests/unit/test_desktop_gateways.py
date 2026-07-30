"""Tests for :class:`reversible_mosaic.android.desktop.DesktopOutputGateway`.

Covers the collision-safe copy (``_1/_2``), no-op view / share on PC, and the
clipboard stub. These aren't strictly Android but they are what our unit-tests
can reach without JNI, and they document the gateway contract the real
:class:`AndroidOutputGateway` also satisfies.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from reversible_mosaic.android.desktop import (
    DesktopClipboardGateway,
    DesktopInputGateway,
    DesktopOutputGateway,
)


def _write_random_png(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


def test_desktop_output_publishes_new_file(tmp_path: Path) -> None:
    gateway = DesktopOutputGateway(tmp_path / "gallery")
    source = tmp_path / "src.png"
    _write_random_png(source, b"payload-1")

    handle = gateway.publish_png(source, "photo_mosaic.png")

    destination = Path(handle)
    assert destination.exists()
    assert destination.name == "photo_mosaic.png"
    assert destination.read_bytes() == b"payload-1"


def test_desktop_output_appends_counter_on_collision(tmp_path: Path) -> None:
    gateway = DesktopOutputGateway(tmp_path / "gallery")
    source_a = tmp_path / "a.png"
    source_b = tmp_path / "b.png"
    _write_random_png(source_a, b"a")
    _write_random_png(source_b, b"b")

    first = gateway.publish_png(source_a, "photo_mosaic.png")
    second = gateway.publish_png(source_b, "photo_mosaic.png")

    assert Path(first).name == "photo_mosaic.png"
    assert Path(second).name == "photo_mosaic_1.png"
    assert Path(first).read_bytes() == b"a"
    assert Path(second).read_bytes() == b"b"


def test_desktop_view_and_share_are_noops(tmp_path: Path) -> None:
    gateway = DesktopOutputGateway(tmp_path)
    # These must not raise on the PC path; they intentionally return None.
    gateway.open_for_view("anything")
    gateway.share("anything", "subject")


def test_desktop_input_imports_to_cache(tmp_path: Path) -> None:
    gateway = DesktopInputGateway()
    cache = tmp_path / "cache"
    src = tmp_path / "orig.jpg"
    src.write_bytes(b"hello")

    destination = gateway.import_to_cache(str(src), cache)

    assert destination.exists()
    assert destination.parent == cache
    assert destination.suffix == ".jpg"
    assert (
        hashlib.sha256(destination.read_bytes()).hexdigest()
        == hashlib.sha256(b"hello").hexdigest()
    )


def test_desktop_clipboard_is_noop() -> None:
    gateway = DesktopClipboardGateway()
    # Just needs to not raise.
    gateway.copy_sensitive("500000")
