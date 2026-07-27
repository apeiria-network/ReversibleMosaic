"""End-to-end local processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from reversible_mosaic.core.algorithm.contracts import CancellationProbe, PixelArray
from reversible_mosaic.core.algorithm.registry import get, latest
from reversible_mosaic.domain.share_code import ShareCode, parse_share_code
from reversible_mosaic.domain.tasks import ProgressReporter
from reversible_mosaic.io.normalize import NormalizedImage, normalize_image, write_png
from reversible_mosaic.io.png_metadata import MosaicMetadata

STAGE_NORMALIZE = "normalize"
STAGE_TRANSFORM = "transform"
STAGE_WRITE = "write"


@dataclass(frozen=True, slots=True)
class PipelineResult:
    output_path: Path
    pixels: PixelArray
    source: NormalizedImage
    algorithm_version: int
    rounds: int
    share_code: ShareCode


def process_image(
    input_path: str | Path,
    output_path: str | Path,
    *,
    operation: Literal["encrypted", "restored"],
    rounds: int,
    share_code: str | None,
    algorithm_version: int | None = None,
    cancel: CancellationProbe | None = None,
    progress: ProgressReporter | None = None,
) -> PipelineResult:
    """Normalize, transform, encode, and verify one image."""
    if progress is not None:
        progress.report(STAGE_NORMALIZE, 0.0)
    source = normalize_image(input_path)
    code = parse_share_code(share_code)
    if operation == "encrypted":
        descriptor = latest()
    else:
        descriptor = get(algorithm_version or latest().version)
    if progress is not None:
        progress.report(STAGE_TRANSFORM, 0.0)
    transform = descriptor.encrypt if operation == "encrypted" else descriptor.decrypt
    output_pixels = transform(source.pixels, code.seed, rounds, cancel)
    metadata = MosaicMetadata(
        schema_version=1,
        app_marker="reversible_mosaic",
        operation_type=operation,
        algorithm_version=descriptor.version,
        rounds=rounds,  # type: ignore[arg-type]
        pixel_mode=source.mode,  # type: ignore[arg-type]
        width=source.width,
        height=source.height,
    )
    if progress is not None:
        progress.report(STAGE_WRITE, 0.0)
    destination = Path(output_path)
    write_png(destination, output_pixels, metadata)
    return PipelineResult(destination, output_pixels, source, descriptor.version, rounds, code)
