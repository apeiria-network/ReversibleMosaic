"""Cancellation and progress tokens for cooperative multitasking."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

ProgressCallback = Callable[[str, float | None], None]


@dataclass(slots=True)
class CancellationToken:
    """Thread-safe cooperative cancellation flag."""

    _flag: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self._flag.set()

    def is_cancelled(self) -> bool:
        return self._flag.is_set()

    def probe(self) -> bool:
        return self._flag.is_set()

    def reset(self) -> None:
        self._flag.clear()


@dataclass(slots=True)
class ProgressReporter:
    """Coalesces progress updates so the UI never floods the event loop."""

    _callback: ProgressCallback | None = None

    def bind(self, callback: ProgressCallback | None) -> None:
        self._callback = callback

    def report(self, stage: str, fraction: float | None = None) -> None:
        if self._callback is not None:
            self._callback(stage, fraction)
