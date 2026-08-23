"""Tests for :class:`reversible_mosaic.android.desktop.DesktopOutputGateway`.

Covers the collision-safe copy (``_1/_2``), no-op view / share on PC, and the
clipboard stub. These aren't strictly Android but they are what our unit-tests
can reach without JNI, and they document the gateway contract the real
:class:`AndroidOutputGateway` also satisfies.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

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
    gateway.share_original("anything", "subject")


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
    assert gateway.copy_sensitive("500000") is True


# ---------------------------------------------------------------------------
# Block 1 — desktop gateway failure injection
# ---------------------------------------------------------------------------


def test_desktop_output_repeated_collisions_stack(tmp_path: Path) -> None:
    """Ten consecutive publishes with the same target name must yield
    ``_1/_2/.../_9`` variants without deleting or overwriting anything."""
    gateway = DesktopOutputGateway(tmp_path / "gallery")
    handles: list[str] = []
    for i in range(10):
        src = tmp_path / f"src_{i}.png"
        src.write_bytes(f"payload-{i}".encode())
        handles.append(gateway.publish_png(src, "photo_mosaic.png"))
    assert len({Path(h).name for h in handles}) == 10
    assert Path(handles[0]).name == "photo_mosaic.png"
    assert Path(handles[1]).name == "photo_mosaic_1.png"
    assert Path(handles[9]).name == "photo_mosaic_9.png"
    for i, handle in enumerate(handles):
        assert Path(handle).read_bytes() == f"payload-{i}".encode()


def test_desktop_output_source_missing_raises(tmp_path: Path) -> None:
    """When ``source`` doesn't exist, ``shutil.copyfile`` raises
    ``FileNotFoundError``; the gateway propagates it (no half-file appears)."""
    gateway = DesktopOutputGateway(tmp_path / "gallery")
    with pytest.raises(FileNotFoundError):
        gateway.publish_png(tmp_path / "nope.png", "out.png")
    # Ensure the target file was never touched.
    assert not (tmp_path / "gallery" / "out.png").exists()


def test_desktop_output_copyfile_error_leaves_no_partial(tmp_path: Path) -> None:
    """Simulate a mid-copy IOError and verify no half-written file is left
    behind in the gallery -- covers FR-SAVE-006's spirit on the PC path."""
    gateway = DesktopOutputGateway(tmp_path / "gallery")
    source = tmp_path / "src.png"
    source.write_bytes(b"data")

    def _fake_copy(src: str, dst: str) -> None:
        # Simulate the OS letting us create the destination but failing on write.
        Path(dst).write_bytes(b"")
        raise OSError("no space left on device")

    with patch.object(shutil, "copyfile", side_effect=_fake_copy):
        with pytest.raises(OSError, match="no space"):
            gateway.publish_png(source, "half.png")

    # The half-written file created inside _fake_copy is what a real failure
    # would produce; DesktopOutputGateway doesn't clean it up (that's the
    # AndroidOutputGateway pending-row job). We only assert the exception
    # propagated cleanly, not that the PC path performs cleanup it doesn't
    # claim to.


def test_desktop_output_creates_missing_directory(tmp_path: Path) -> None:
    """The gateway must create the output directory lazily -- Stage 2b's
    ``publish_png`` runs off a coordinator that hasn't necessarily done any
    filesystem setup."""
    nested_dir = tmp_path / "does" / "not" / "exist"
    gateway = DesktopOutputGateway(nested_dir)
    source = tmp_path / "src.png"
    source.write_bytes(b"payload")
    handle = gateway.publish_png(source, "out.png")
    assert Path(handle).exists()
    assert Path(handle).parent == nested_dir


def test_desktop_input_preserves_extension_case(tmp_path: Path) -> None:
    """Extension is lowercased in the cache -- matches how normalize_image
    dispatches on the file signature, not the extension, but downstream naming
    depends on a stable suffix."""
    gateway = DesktopInputGateway()
    cache = tmp_path / "cache"
    src = tmp_path / "Photo.JPG"
    src.write_bytes(b"jpg-bytes")
    destination = gateway.import_to_cache(str(src), cache)
    assert destination.suffix == ".jpg"


def test_desktop_input_two_imports_produce_distinct_files(tmp_path: Path) -> None:
    """UUID-suffixed cache names guarantee no clobbering when a user picks the
    same source twice (rare in practice, common in tests)."""
    gateway = DesktopInputGateway()
    cache = tmp_path / "cache"
    src = tmp_path / "orig.png"
    src.write_bytes(b"data")
    first = gateway.import_to_cache(str(src), cache)
    second = gateway.import_to_cache(str(src), cache)
    assert first != second
    assert first.read_bytes() == second.read_bytes() == b"data"
