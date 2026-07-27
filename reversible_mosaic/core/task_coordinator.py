"""Threaded coordinator that runs the pipeline off the UI thread."""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from reversible_mosaic.core.pipeline import (
    STAGE_NORMALIZE,
    STAGE_TRANSFORM,
    STAGE_WRITE,
    PipelineResult,
    process_image,
)
from reversible_mosaic.domain.task_state import InvalidTaskTransition, TaskState, transition
from reversible_mosaic.domain.tasks import CancellationToken, ProgressReporter

Operation = Literal["encrypted", "restored"]
MainThreadScheduler = Callable[[Callable[[], None]], None]


def _run_now(callback: Callable[[], None]) -> None:
    """Default scheduler: run the callback synchronously in the calling thread.

    Kivy replaces this with ``Clock.schedule_once`` so widgets are only touched
    on the UI thread. Tests can inject a deterministic scheduler.
    """
    callback()


@dataclass(frozen=True, slots=True)
class TaskRequest:
    operation: Operation
    input_path: Path
    output_path: Path
    rounds: int
    share_code: str | None
    algorithm_version: int | None = None


class TaskCoordinatorError(RuntimeError):
    """Raised when a caller violates the coordinator's contract."""


class TaskCoordinator:
    """Owns the worker thread, cancellation flag, progress reporter, and state."""

    def __init__(self, schedule_on_main: MainThreadScheduler | None = None):
        self._schedule = schedule_on_main or _run_now
        self._lock = threading.Lock()
        self._state = TaskState.IDLE
        self._thread: threading.Thread | None = None
        self._cancel = CancellationToken()
        self._progress = ProgressReporter()
        self._last_stage: str | None = None
        self.on_state_change: Callable[[TaskState, TaskState], None] | None = None
        self.on_progress: Callable[[str, float | None], None] | None = None
        self.on_completed: Callable[[PipelineResult], None] | None = None
        self.on_failed: Callable[[BaseException], None] | None = None
        self.on_cancelled: Callable[[], None] | None = None

    @property
    def state(self) -> TaskState:
        with self._lock:
            return self._state

    def start(self, request: TaskRequest) -> None:
        """Begin processing. Raises if a task is already active."""
        with self._lock:
            if self._state not in (TaskState.IDLE,):
                message = f"已有任务处于 {self._state.value}，无法启动新任务。"  # noqa: RUF001
                raise TaskCoordinatorError(message)
            self._transition_locked(TaskState.IMAGE_SELECTED)
            self._cancel.reset()
            self._last_stage = None
            self._progress.bind(self._forward_progress)
            self._thread = threading.Thread(
                target=self._run,
                args=(request,),
                name=f"reversible-mosaic-{request.operation}",
                daemon=True,
            )
        self._thread.start()

    def cancel(self) -> None:
        """Request cooperative cancellation; safe to call from the UI thread."""
        self._cancel.cancel()

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _run(self, request: TaskRequest) -> None:
        try:
            result = process_image(
                request.input_path,
                request.output_path,
                operation=request.operation,
                rounds=request.rounds,
                share_code=request.share_code,
                algorithm_version=request.algorithm_version,
                cancel=self._cancel.probe,
                progress=self._progress,
            )
        except BaseException as exc:
            if self._cancel.is_cancelled():
                self._deliver_cancelled()
            else:
                self._deliver_failed(exc)
            return
        self._deliver_completed(result)

    def _forward_progress(self, stage: str, fraction: float | None) -> None:
        with self._lock:
            self._sync_state_to_stage_locked(stage)
        callback = self.on_progress
        if callback is None:
            return
        self._schedule(lambda: callback(stage, fraction))

    def _sync_state_to_stage_locked(self, stage: str) -> None:
        if stage == self._last_stage:
            return
        self._last_stage = stage
        if stage == STAGE_NORMALIZE and self._state is TaskState.IMAGE_SELECTED:
            self._transition_locked(TaskState.NORMALIZING)
        elif stage == STAGE_TRANSFORM and self._state is TaskState.NORMALIZING:
            self._transition_locked(TaskState.NORMALIZED)
            self._transition_locked(TaskState.PROCESSING)
        elif stage == STAGE_WRITE and self._state is TaskState.PROCESSING:
            # PNG write happens under PROCESSING; state stays put but progress
            # callback still fires so the UI can render the new stage label.
            return

    def _deliver_completed(self, result: PipelineResult) -> None:
        self._transition(TaskState.PREVIEW_READY)
        callback = self.on_completed
        if callback is not None:
            self._schedule(lambda: callback(result))

    def _deliver_failed(self, exc: BaseException) -> None:
        self._transition(TaskState.FAILED)
        callback = self.on_failed
        if callback is not None:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
            self._schedule(lambda: callback(exc))

    def _deliver_cancelled(self) -> None:
        self._transition(TaskState.CANCELLED)
        callback = self.on_cancelled
        if callback is not None:
            self._schedule(callback)

    def _transition(self, target: TaskState) -> None:
        with self._lock:
            self._transition_locked(target)

    def _transition_locked(self, target: TaskState) -> None:
        try:
            new_state = transition(self._state, target)
        except InvalidTaskTransition:
            raise
        old_state = self._state
        self._state = new_state
        callback = self.on_state_change
        if callback is not None:
            self._schedule(lambda: callback(old_state, new_state))

    def reset(self) -> None:
        """Return to IDLE after a completed / failed / cancelled task."""
        with self._lock:
            if self._state in (
                TaskState.PREVIEW_READY,
                TaskState.FAILED,
                TaskState.CANCELLED,
                TaskState.COMMITTED,
            ):
                self._transition_locked(TaskState.IDLE)
            elif self._state != TaskState.IDLE:
                message = f"任务处于 {self._state.value}，不能直接重置。"  # noqa: RUF001
                raise TaskCoordinatorError(message)
