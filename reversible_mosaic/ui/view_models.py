"""Kivy screens: encode/decode form, progress, and result.

These modules import Kivy lazily so that domain- and core-layer tests keep
running on machines that do not have the app extra installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reversible_mosaic.core.pipeline import PipelineResult
from reversible_mosaic.domain.share_code import (
    ShareCodeError,
    generate_share_code,
    parse_share_code,
)

VALID_ROUNDS = (2, 5, 15, 30)
DEFAULT_ROUNDS = 5


@dataclass(slots=True)
class TaskFormState:
    """UI-facing snapshot of the encode/decode form."""

    operation: str  # "encrypted" or "restored"
    input_path: Path | None = None
    share_code: str = ""
    rounds: int = DEFAULT_ROUNDS
    algorithm_version: int | None = None  # decode-only; encode always uses latest

    def parsed_share_code(self) -> str | None:
        """Return the normalized share code or raise ``ShareCodeError``."""
        cleaned = self.share_code.strip()
        return parse_share_code(cleaned if cleaned else None).normalized

    def randomize_share_code(self) -> None:
        self.share_code = generate_share_code().normalized

    def can_start(self) -> bool:
        if self.input_path is None:
            return False
        if self.rounds not in VALID_ROUNDS:
            return False
        try:
            self.parsed_share_code()
        except ShareCodeError:
            return False
        return True


@dataclass(slots=True)
class ProgressSnapshot:
    """Data pushed from the coordinator to the progress screen."""

    stage: str
    fraction: float | None
    label: str

    @classmethod
    def from_stage(cls, stage: str, fraction: float | None) -> ProgressSnapshot:
        labels = {
            "normalize": "规范化",
            "transform": "算法处理",
            "write": "写入 PNG",
        }
        return cls(stage=stage, fraction=fraction, label=labels.get(stage, stage))


@dataclass(slots=True)
class ResultSnapshot:
    """Metadata surfaced on the result screen after a successful task."""

    output_path: Path
    algorithm_version: int
    rounds: int
    share_code_display: str

    @classmethod
    def from_pipeline(cls, result: PipelineResult) -> ResultSnapshot:
        return cls(
            output_path=result.output_path,
            algorithm_version=result.algorithm_version,
            rounds=result.rounds,
            share_code_display=result.share_code.normalized,
        )
