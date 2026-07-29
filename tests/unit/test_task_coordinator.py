"""End-to-end tests for the threaded task coordinator."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from reversible_mosaic.core.task_coordinator import (
    TaskCoordinator,
    TaskCoordinatorError,
    TaskRequest,
)
from reversible_mosaic.domain.task_state import TaskState


def _write_rgb_png(path: Path, width: int = 8, height: int = 6) -> None:
    rng = np.random.default_rng(seed=42)
    pixels = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    Image.fromarray(pixels, mode="RGB").save(path, format="PNG")


def _sync_scheduler() -> Callable[[Callable[[], None]], None]:
    """Immediate scheduler so callbacks run in the worker/test thread."""
    return lambda cb: cb()


def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timeout waiting for predicate")


def test_encrypt_then_reset(tmp_path: Path) -> None:
    src = tmp_path / "in.png"
    dst = tmp_path / "out.png"
    _write_rgb_png(src)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    states: list[TaskState] = []
    stages: list[str] = []
    completed = threading.Event()
    coord.on_state_change = lambda _old, new: states.append(new)
    coord.on_progress = lambda stage, _frac: stages.append(stage)
    coord.on_completed = lambda _result: completed.set()

    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst,
            rounds=2,
            share_code="500000",
        )
    )
    coord.join(timeout=10)
    assert completed.wait(timeout=5)
    assert coord.state is TaskState.PREVIEW_READY
    assert dst.exists()
    assert TaskState.NORMALIZING in states
    assert TaskState.PROCESSING in states
    assert TaskState.PREVIEW_READY in states
    assert stages[0] == "normalize"
    assert "transform" in stages
    assert "write" in stages

    coord.reset()
    assert coord.state is TaskState.IDLE


def test_double_start_rejected(tmp_path: Path) -> None:
    src = tmp_path / "in.png"
    dst = tmp_path / "out.png"
    _write_rgb_png(src, width=4, height=4)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    request = TaskRequest(
        operation="encrypted",
        input_path=src,
        output_path=dst,
        rounds=2,
        share_code=None,
    )
    coord.start(request)
    with pytest.raises(TaskCoordinatorError):
        coord.start(request)
    coord.join(timeout=10)


def test_failure_delivers_exception(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.png"
    dst = tmp_path / "out.png"
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    captured: list[BaseException] = []
    coord.on_failed = lambda exc: captured.append(exc)
    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=missing,
            output_path=dst,
            rounds=2,
            share_code=None,
        )
    )
    coord.join(timeout=10)
    assert coord.state is TaskState.FAILED
    assert len(captured) == 1


def test_cancellation_stops_worker(tmp_path: Path) -> None:
    # Use a larger image and 20 rounds so the transform loop has time to poll
    # the cancellation flag before returning.
    src = tmp_path / "in.png"
    dst = tmp_path / "out.png"
    _write_rgb_png(src, width=256, height=256)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    cancelled = threading.Event()
    coord.on_cancelled = cancelled.set

    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst,
            rounds=20,
            share_code=None,
        )
    )

    _wait_until(lambda: coord.state in (TaskState.PROCESSING, TaskState.NORMALIZING))
    coord.cancel()
    coord.join(timeout=15)
    assert cancelled.is_set()
    assert coord.state is TaskState.CANCELLED
    assert not dst.exists()

    coord.reset()
    assert coord.state is TaskState.IDLE
