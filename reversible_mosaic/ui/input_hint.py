"""Input preview helper — read image metadata quickly before starting the pipeline.

Encode/decode screens call :func:`inspect_input` right after the user selects a
file. The returned :class:`InputHint` fuels the preview panel (dimensions,
mode, file size) and, for decode, the auto-populated algorithm version and
rounds from any embedded ``reversible_mosaic`` metadata block.

Preview does NOT enforce the resource limits or JPEG preflight from
:mod:`reversible_mosaic.io.normalize`; those run when the pipeline actually
starts, so an invalid input surfaces there with the full Chinese-language
error path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reversible_mosaic.io.png_metadata import MetadataResult, MetadataStatus, parse_png_metadata
from reversible_mosaic.io.probe import ImageProbeError, scan_png


@dataclass(frozen=True, slots=True)
class InputHint:
    """Non-authoritative preview of a candidate input."""

    path: Path
    format: str
    width: int
    height: int
    mode: str
    file_bytes: int
    metadata: MetadataResult
    error: str | None = None

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @property
    def has_encrypted_metadata(self) -> bool:
        return (
            self.metadata.status is MetadataStatus.VALID
            and self.metadata.metadata is not None
            and self.metadata.metadata.operation_type == "encrypted"
        )

    @property
    def suggested_rounds(self) -> int | None:
        if self.metadata.metadata is None:
            return None
        return self.metadata.metadata.rounds

    @property
    def suggested_algorithm_version(self) -> int | None:
        if self.metadata.metadata is None:
            return None
        return self.metadata.metadata.algorithm_version


_EMPTY_METADATA = MetadataResult(status=MetadataStatus.ABSENT, metadata=None, reason=None)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8"


def _error_hint(path: Path, fmt: str, size: int, error: str) -> InputHint:
    return InputHint(
        path=path,
        format=fmt,
        width=0,
        height=0,
        mode="?",
        file_bytes=size,
        metadata=_EMPTY_METADATA,
        error=error,
    )


def _sniff_format(path: Path) -> str:
    """Detect image format from the first bytes, ignoring the file extension.

    Windows screenshot tools sometimes save JPEG data under a ``.png`` name and
    Android content URIs may drop the extension entirely, so trusting the
    suffix here would cause spurious preview failures.
    """
    try:
        with path.open("rb") as source:
            signature = source.read(16)
    except OSError:
        return "UNKNOWN"
    if signature.startswith(_PNG_SIGNATURE):
        return "PNG"
    if signature.startswith(_JPEG_SIGNATURE):
        return "JPEG"
    return "UNKNOWN"


def inspect_input(path: str | Path) -> InputHint:
    """Return a lightweight :class:`InputHint` without loading full pixels."""
    resolved = Path(path)
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        return _error_hint(resolved, "?", 0, f"无法读取文件: {exc}")

    detected = _sniff_format(resolved)
    if detected == "PNG":
        try:
            probe = scan_png(resolved)
        except ImageProbeError as exc:
            return _error_hint(resolved, "PNG", size, str(exc))
        metadata = parse_png_metadata(
            list(probe.chunks),
            actual_mode=probe.mode,
            actual_size=(probe.width, probe.height),
        )
        return InputHint(
            path=resolved,
            format="PNG",
            width=probe.width,
            height=probe.height,
            mode=probe.mode,
            file_bytes=size,
            metadata=metadata,
        )
    if detected == "JPEG":
        try:
            from PIL import Image

            with Image.open(resolved) as image:
                width, height = image.size
        except Exception as exc:
            return _error_hint(resolved, "JPEG", size, f"JPEG 读取失败: {exc}")
        return InputHint(
            path=resolved,
            format="JPEG",
            width=width,
            height=height,
            mode="RGB",
            file_bytes=size,
            metadata=_EMPTY_METADATA,
        )
    return _error_hint(
        resolved,
        resolved.suffix.lower() or "?",
        size,
        "不支持的格式或文件已损坏 (未识别到 PNG 或 JPEG 签名)。",
    )


def format_file_size(bytes_count: int) -> str:
    """Human-readable size, e.g. ``"1.2 MB"`` — safe for Chinese UI."""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count / (1024 * 1024):.2f} MB"
