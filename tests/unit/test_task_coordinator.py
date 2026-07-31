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


# ---------------------------------------------------------------------------
# Block 1 — restart, reset guards, and lifecycle edge cases
# ---------------------------------------------------------------------------


def test_restart_after_cancel(tmp_path: Path) -> None:
    """After a cancelled run resets, the coordinator must accept a new task."""
    src = tmp_path / "in.png"
    dst_a = tmp_path / "out_a.png"
    dst_b = tmp_path / "out_b.png"
    _write_rgb_png(src, width=64, height=64)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    cancelled = threading.Event()
    completed = threading.Event()
    coord.on_cancelled = cancelled.set
    coord.on_completed = lambda _result: completed.set()

    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst_a,
            rounds=20,
            share_code=None,
        )
    )
    _wait_until(lambda: coord.state in (TaskState.PROCESSING, TaskState.NORMALIZING))
    coord.cancel()
    coord.join(timeout=15)
    assert cancelled.is_set()

    coord.reset()
    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst_b,
            rounds=2,
            share_code=None,
        )
    )
    coord.join(timeout=10)
    assert completed.wait(timeout=5)
    assert coord.state is TaskState.PREVIEW_READY
    assert dst_b.exists()


def test_restart_after_failure(tmp_path: Path) -> None:
    """A failed task must be resettable and the coordinator reusable."""
    missing = tmp_path / "does_not_exist.png"
    dst = tmp_path / "out.png"
    src = tmp_path / "real.png"
    _write_rgb_png(src, width=8, height=8)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    failure = threading.Event()
    completed = threading.Event()
    coord.on_failed = lambda _exc: failure.set()
    coord.on_completed = lambda _result: completed.set()

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
    assert failure.is_set()
    assert coord.state is TaskState.FAILED

    coord.reset()
    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst,
            rounds=2,
            share_code=None,
        )
    )
    coord.join(timeout=10)
    assert completed.wait(timeout=5)
    assert coord.state is TaskState.PREVIEW_READY


def test_reset_rejected_in_active_state(tmp_path: Path) -> None:
    """``reset`` must refuse mid-flight states (IMAGE_SELECTED, NORMALIZING,
    PROCESSING). Otherwise a caller could sneak a new task in on top of a
    running worker."""
    src = tmp_path / "in.png"
    dst = tmp_path / "out.png"
    _write_rgb_png(src, width=128, height=128)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst,
            rounds=20,
            share_code=None,
        )
    )
    _wait_until(lambda: coord.state != TaskState.IDLE)
    with pytest.raises(TaskCoordinatorError, match="不能直接重置"):
        coord.reset()
    coord.cancel()
    coord.join(timeout=15)


def test_reset_from_idle_is_noop() -> None:
    """Calling ``reset`` when already IDLE must not raise -- otherwise repeated
    result-page returns would blow up."""
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    assert coord.state is TaskState.IDLE
    coord.reset()  # no-op
    assert coord.state is TaskState.IDLE


def test_no_callbacks_still_completes(tmp_path: Path) -> None:
    """The coordinator must not require any callback to be attached; missing
    hooks are a legitimate configuration (e.g. batch scripts)."""
    src = tmp_path / "in.png"
    dst = tmp_path / "out.png"
    _write_rgb_png(src, width=8, height=8)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    # Deliberately leave every on_* callback as None.
    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst,
            rounds=2,
            share_code=None,
        )
    )
    coord.join(timeout=10)
    assert coord.state is TaskState.PREVIEW_READY
    assert dst.exists()


def test_cancel_before_start_is_noop(tmp_path: Path) -> None:
    """Calling ``cancel`` when nothing is running must not raise and must not
    poison the next ``start``."""
    src = tmp_path / "in.png"
    dst = tmp_path / "out.png"
    _write_rgb_png(src, width=8, height=8)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    coord.cancel()  # nothing running
    completed = threading.Event()
    coord.on_completed = lambda _result: completed.set()
    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst,
            rounds=2,
            share_code=None,
        )
    )
    coord.join(timeout=10)
    assert completed.wait(timeout=5)
    # start() must have reset the cancellation flag; the run should complete.
    assert coord.state is TaskState.PREVIEW_READY


def test_concurrent_double_start_only_admits_one(tmp_path: Path) -> None:
    """Two threads racing on ``start`` must land exactly one success and one
    :class:`TaskCoordinatorError`."""
    src = tmp_path / "in.png"
    dst_a = tmp_path / "a.png"
    dst_b = tmp_path / "b.png"
    _write_rgb_png(src, width=32, height=32)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    successes = 0
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)
    lock = threading.Lock()

    def _try_start(dst: Path) -> None:
        nonlocal successes
        barrier.wait()
        try:
            coord.start(
                TaskRequest(
                    operation="encrypted",
                    input_path=src,
                    output_path=dst,
                    rounds=2,
                    share_code=None,
                )
            )
            with lock:
                successes += 1
        except BaseException as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_try_start, args=(dst_a,))
    t2 = threading.Thread(target=_try_start, args=(dst_b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    coord.join(timeout=10)
    assert successes == 1
    assert len(errors) == 1
    assert isinstance(errors[0], TaskCoordinatorError)


def test_progress_carries_stage_and_fraction(tmp_path: Path) -> None:
    """Progress callbacks must forward stage names verbatim and forward
    fractions untouched (rounding is the UI's problem)."""
    src = tmp_path / "in.png"
    dst = tmp_path / "out.png"
    _write_rgb_png(src, width=16, height=16)
    coord = TaskCoordinator(schedule_on_main=_sync_scheduler())
    seen: list[tuple[str, float | None]] = []
    completed = threading.Event()
    coord.on_progress = lambda stage, frac: seen.append((stage, frac))
    coord.on_completed = lambda _result: completed.set()
    coord.start(
        TaskRequest(
            operation="encrypted",
            input_path=src,
            output_path=dst,
            rounds=2,
            share_code=None,
        )
    )
    coord.join(timeout=10)
    assert completed.wait(timeout=5)
    stages = [s for s, _f in seen]
    assert "normalize" in stages
    assert "transform" in stages
    assert "write" in stages
    for _stage, frac in seen:
        if frac is not None:
            assert 0.0 <= frac <= 1.0
