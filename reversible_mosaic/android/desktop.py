"""Desktop-only stand-in gateways for use during PC verification."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path


class DesktopInputGateway:
    def import_to_cache(self, uri: str, cache_dir: Path) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        source = Path(uri)
        destination = cache_dir / f"in_{uuid.uuid4().hex}{source.suffix.lower()}"
        shutil.copyfile(source, destination)
        return destination


class DesktopOutputGateway:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def publish_png(self, source: Path, display_name: str) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / display_name
        counter = 0
        while destination.exists():
            counter += 1
            stem = Path(display_name).stem
            suffix = Path(display_name).suffix
            destination = self.output_dir / f"{stem}_{counter}{suffix}"
        shutil.copyfile(source, destination)
        return str(destination)

    def open_for_view(self, handle: str) -> None:
        return None


class DesktopClipboardGateway:
    def copy_sensitive(self, text: str) -> bool:
        return True
