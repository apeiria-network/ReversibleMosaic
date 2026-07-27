"""Processing task state transitions."""

from __future__ import annotations

from enum import StrEnum


class TaskState(StrEnum):
    IDLE = "idle"
    IMAGE_SELECTED = "image_selected"
    NORMALIZING = "normalizing"
    NORMALIZED = "normalized"
    PROCESSING = "processing"
    PREVIEW_READY = "preview_ready"
    SAVING = "saving"
    COMMITTED = "committed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.IDLE: frozenset({TaskState.IMAGE_SELECTED}),
    TaskState.IMAGE_SELECTED: frozenset({TaskState.NORMALIZING, TaskState.IDLE}),
    TaskState.NORMALIZING: frozenset(
        {TaskState.NORMALIZED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.NORMALIZED: frozenset({TaskState.PROCESSING, TaskState.IDLE}),
    TaskState.PROCESSING: frozenset(
        {TaskState.PREVIEW_READY, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.PREVIEW_READY: frozenset({TaskState.PROCESSING, TaskState.SAVING, TaskState.IDLE}),
    TaskState.SAVING: frozenset(
        {TaskState.COMMITTED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.COMMITTED: frozenset({TaskState.IDLE}),
    TaskState.FAILED: frozenset({TaskState.IDLE, TaskState.PROCESSING, TaskState.SAVING}),
    TaskState.CANCELLED: frozenset({TaskState.IDLE, TaskState.PROCESSING}),
}


class InvalidTaskTransition(RuntimeError):
    """Raised when code attempts an unsafe task-state transition."""


def transition(current: TaskState, target: TaskState) -> TaskState:
    """Validate and return the next state."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidTaskTransition(f"不允许从 {current.value} 切换到 {target.value}。")
    return target
