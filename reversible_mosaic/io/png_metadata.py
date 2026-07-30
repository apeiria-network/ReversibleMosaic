"""Strict reversible_mosaic PNG metadata protocol."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Literal

METADATA_KEYWORD = b"reversible_mosaic"
MAX_VALUE_BYTES = 2048
MAX_CANDIDATES = 4
MAX_TOTAL_TEXT_BYTES = 64 * 1024
_TEXT_CHUNKS = frozenset({b"tEXt", b"zTXt", b"iTXt"})


class MetadataStatus(StrEnum):
    VALID = "valid"
    ABSENT = "absent"
    INVALID = "invalid"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class MosaicMetadata:
    schema_version: int
    app_marker: str
    operation_type: Literal["encrypted", "restored"]
    algorithm_version: int
    rounds: Literal[1, 5, 10, 20]
    pixel_mode: Literal["RGB", "RGBA"]
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class MetadataResult:
    status: MetadataStatus
    metadata: MosaicMetadata | None = None
    reason: str | None = None


def serialize_metadata(metadata: MosaicMetadata) -> str:
    """Serialize a validated, deterministic ASCII-only JSON object."""
    _validate(metadata)
    value = json.dumps(asdict(metadata), ensure_ascii=True, separators=(",", ":"))
    encoded = value.encode("ascii")
    if len(encoded) > MAX_VALUE_BYTES:
        raise ValueError("辅助元数据超过 2048 字节。")
    return value


def parse_png_metadata(
    chunks: list[tuple[bytes, bytes]],
    *,
    actual_mode: str | None = None,
    actual_size: tuple[int, int] | None = None,
) -> MetadataResult:
    """Parse pre-bounded raw PNG chunks without decompressing text."""
    total = sum(len(data) for kind, data in chunks if kind in _TEXT_CHUNKS)
    if total > MAX_TOTAL_TEXT_BYTES:
        return MetadataResult(MetadataStatus.INVALID, reason="PNG 文本元数据累计超限。")

    candidates: list[tuple[bytes, bytes]] = []
    for kind, data in chunks:
        keyword = data.split(b"\x00", 1)[0]
        if kind in _TEXT_CHUNKS and keyword == METADATA_KEYWORD:
            candidates.append((kind, data))
            if len(candidates) > MAX_CANDIDATES:
                return MetadataResult(MetadataStatus.INVALID, reason="同名元数据候选过多。")
    if not candidates:
        return MetadataResult(MetadataStatus.ABSENT)
    if len(candidates) != 1:
        return MetadataResult(MetadataStatus.INVALID, reason="同名元数据重复。")

    kind, candidate = candidates[0]
    if kind != b"tEXt":
        return MetadataResult(MetadataStatus.INVALID, reason="协议只接受未压缩 tEXt。")
    _, separator, raw_value = candidate.partition(b"\x00")
    if not separator or len(raw_value) > MAX_VALUE_BYTES:
        return MetadataResult(MetadataStatus.INVALID, reason="元数据格式或长度无效。")
    try:
        text = raw_value.decode("ascii")
        raw = json.loads(text)
        metadata = _from_mapping(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return MetadataResult(MetadataStatus.INVALID, reason=f"元数据无效: {exc}")

    if actual_mode is not None and metadata.pixel_mode != actual_mode:
        return MetadataResult(MetadataStatus.CONFLICT, metadata, "元数据模式与实际图片冲突。")
    if actual_size is not None and (metadata.width, metadata.height) != actual_size:
        return MetadataResult(MetadataStatus.CONFLICT, metadata, "元数据尺寸与实际图片冲突。")
    return MetadataResult(MetadataStatus.VALID, metadata)


def _from_mapping(raw: Any) -> MosaicMetadata:
    if not isinstance(raw, dict) or any(isinstance(value, (dict, list)) for value in raw.values()):
        raise ValueError("JSON 必须是非嵌套对象。")
    required = {
        "schema_version",
        "app_marker",
        "operation_type",
        "algorithm_version",
        "rounds",
        "pixel_mode",
        "width",
        "height",
    }
    if not required.issubset(raw):
        raise ValueError("缺少必需字段。")
    values = {key: raw[key] for key in required}
    numeric_keys = ("schema_version", "algorithm_version", "rounds", "width", "height")
    if any(type(values[key]) is not int for key in numeric_keys):
        raise ValueError("整数类型字段无效。")
    metadata = MosaicMetadata(**values)
    _validate(metadata)
    return metadata


def _validate(metadata: MosaicMetadata) -> None:
    if metadata.schema_version != 1 or metadata.app_marker != "reversible_mosaic":
        raise ValueError("schema 或应用标记不受支持。")
    if metadata.operation_type not in ("encrypted", "restored"):
        raise ValueError("操作类型无效。")
    if metadata.algorithm_version <= 0 or metadata.rounds not in (2, 5, 15, 30):
        raise ValueError("算法版本或轮数无效。")
    if metadata.pixel_mode not in ("RGB", "RGBA"):
        raise ValueError("像素模式无效。")
    if metadata.width <= 0 or metadata.height <= 0:
        raise ValueError("图片尺寸无效。")
