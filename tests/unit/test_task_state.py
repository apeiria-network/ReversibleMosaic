from __future__ import annotations

import pytest

from reversible_mosaic.domain.task_state import (
    InvalidTaskTransition,
    TaskState,
    transition,
)


def test_happy_path() -> None:
    state = TaskState.IDLE
    for target in (
        TaskState.IMAGE_SELECTED,
        TaskState.NORMALIZING,
        TaskState.NORMALIZED,
        TaskState.PROCESSING,
        TaskState.PREVIEW_READY,
        TaskState.SAVING,
        TaskState.COMMITTED,
        TaskState.IDLE,
    ):
        state = transition(state, target)
    assert state is TaskState.IDLE


def test_duplicate_processing_is_rejected() -> None:
    with pytest.raises(InvalidTaskTransition):
        transition(TaskState.PROCESSING, TaskState.PROCESSING)
