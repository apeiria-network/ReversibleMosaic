"""Interfaces platform adapters must satisfy."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class InputGateway(Protocol):
    """Reads a chosen image URI safely into an app-private path."""

    def import_to_cache(self, uri: str, cache_dir: Path) -> Path: ...


class OutputGateway(Protocol):
    """Publishes a verified PNG through the platform storage API."""

    def publish_png(self, source: Path, display_name: str) -> str:
        """Return the platform-specific URI/handle of the persisted file."""

    def open_for_view(self, handle: str) -> None: ...

    def share(self, handle: str, subject: str) -> None: ...


class ClipboardGateway(Protocol):
    """Copies a share code and flags it as sensitive if the OS supports it."""

    def copy_sensitive(self, text: str) -> bool: ...
