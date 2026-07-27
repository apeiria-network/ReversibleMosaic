"""Bounded PNG container scanning."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from reversible_mosaic.domain.limits import (
    MAX_INPUT_BYTES,
    MAX_PNG_TEXT_BYTES,
    ResourceLimitError,
    validate_dimensions,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_CHUNK_BYTES = 50 * 1024 * 1024


class ImageProbeError(ValueError):
    """Raised when an input is unsupported or structurally unsafe."""


@dataclass(frozen=True, slots=True)
class PngProbe:
    width: int
    height: int
    mode: str
    chunks: tuple[tuple[bytes, bytes], ...]


def scan_png(path: str | Path) -> PngProbe:
    """Validate a P0 PNG and retain only bounded text chunks."""
    source = Path(path)
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ImageProbeError("输入文件超过 50 MiB。")
    kept: list[tuple[bytes, bytes]] = []
    text_bytes = 0
    seen_ihdr = False
    seen_iend = False
    width = height = 0
    mode = ""
    with source.open("rb") as stream:
        if stream.read(8) != PNG_SIGNATURE:
            raise ImageProbeError("文件不是有效 PNG。")
        while not seen_iend:
            header = stream.read(8)
            if len(header) != 8:
                raise ImageProbeError("PNG 被截断。")
            length, kind = struct.unpack(">I4s", header)
            if length > MAX_CHUNK_BYTES:
                raise ImageProbeError("PNG chunk 长度超限。")
            data = stream.read(length)
            crc_bytes = stream.read(4)
            if len(data) != length or len(crc_bytes) != 4:
                raise ImageProbeError("PNG chunk 被截断。")
            expected_crc = struct.unpack(">I", crc_bytes)[0]
            if zlib.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
                raise ImageProbeError("PNG CRC 校验失败。")
            if kind == b"IHDR":
                if seen_ihdr or length != 13:
                    raise ImageProbeError("PNG IHDR 无效。")
                width, height, depth, color_type, compression, filtering, interlace = struct.unpack(
                    ">IIBBBBB", data
                )
                if depth != 8 or color_type not in (2, 6):
                    raise ImageProbeError("仅支持 8 位 RGB/RGBA PNG。")
                if compression != 0 or filtering != 0 or interlace not in (0, 1):
                    raise ImageProbeError("PNG 编码参数不受支持。")
                try:
                    validate_dimensions(width, height)
                except ResourceLimitError as exc:
                    raise ImageProbeError(str(exc)) from exc
                mode = "RGB" if color_type == 2 else "RGBA"
                seen_ihdr = True
            elif kind == b"acTL":
                raise ImageProbeError("不支持动画 PNG。")
            elif kind in (b"tEXt", b"zTXt", b"iTXt"):
                text_bytes += len(data)
                if text_bytes > MAX_PNG_TEXT_BYTES:
                    raise ImageProbeError("PNG 文本元数据累计超过 64 KiB。")
                kept.append((kind, data))
            elif kind == b"IEND":
                seen_iend = True
        if stream.read(1):
            raise ImageProbeError("PNG 末尾包含额外数据。")
    if not seen_ihdr:
        raise ImageProbeError("PNG 缺少 IHDR。")
    return PngProbe(width, height, mode, tuple(kept))
