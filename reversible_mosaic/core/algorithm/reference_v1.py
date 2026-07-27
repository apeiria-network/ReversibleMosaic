"""Reference implementation of the not-yet-released V1 pixel protocol.

The byte-level behavior in this module becomes immutable only after the V1
specification and fixed vectors are explicitly marked frozen.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterator

from reversible_mosaic.core.algorithm.contracts import (
    VALID_ROUNDS,
    AlgorithmError,
    CancellationProbe,
    CancellationRequested,
    ImageSpec,
    PixelArray,
    validate_pixels,
)

_MASK64 = (1 << 64) - 1
_DOMAIN = b"reversible_mosaic/algorithm/v1\x00"


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & _MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
    return (value ^ (value >> 31)) & _MASK64


def _derive_words(spec: ImageSpec, seed: int) -> tuple[int, int, int, int]:
    if not 0 <= seed <= 9_999_999_999:
        raise AlgorithmError("扰动种子超出 V1 允许范围。")
    mode_id = 3 if spec.mode == "RGB" else 4
    payload = _DOMAIN + struct.pack("<QIIIB", seed, spec.width, spec.height, 1, mode_id)
    return struct.unpack("<QQQQ", hashlib.sha256(payload).digest())


def _round_key(word: int, round_index: int, domain: int) -> int:
    return _splitmix64(word ^ (round_index * 0xD1342543DE82EF95) ^ domain)


def _mask3(key: int, index: int) -> tuple[int, int, int]:
    value = _splitmix64(key ^ index)
    return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF


def _checkpoint(cancel: CancellationProbe | None) -> None:
    if cancel is not None and cancel():
        raise CancellationRequested("处理已取消。")


def _lift_forward(flat: PixelArray, key: int) -> None:
    for index, pixel in enumerate(flat):
        m0, m1, m2 = _mask3(key, index)
        r, g, b = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
        r = (r + 3 * g + 5 * b + m0) & 0xFF
        g = (g + 5 * b + 7 * r + m1) & 0xFF
        b = (b + 7 * r + 3 * g + m2) & 0xFF
        pixel[0], pixel[1], pixel[2] = r, g, b


def _lift_inverse(flat: PixelArray, key: int) -> None:
    for index, pixel in enumerate(flat):
        m0, m1, m2 = _mask3(key, index)
        r, g, b = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
        b = (b - 7 * r - 3 * g - m2) & 0xFF
        g = (g - 5 * b - 7 * r - m1) & 0xFF
        r = (r - 3 * g - 5 * b - m0) & 0xFF
        pixel[0], pixel[1], pixel[2] = r, g, b


def _swap_sequence(length: int, key: int) -> Iterator[tuple[int, int]]:
    for index in range(length - 1, 0, -1):
        random_word = _splitmix64(key ^ index)
        yield index, (random_word * (index + 1)) >> 64


def _permute_forward(flat: PixelArray, key: int) -> None:
    for index, other in _swap_sequence(len(flat), key):
        flat[[index, other]] = flat[[other, index]]


def _permute_inverse(flat: PixelArray, key: int) -> None:
    for index in range(1, len(flat)):
        random_word = _splitmix64(key ^ index)
        other = (random_word * (index + 1)) >> 64
        flat[[index, other]] = flat[[other, index]]


def _diffuse_forward(flat: PixelArray, key: int, reverse: bool) -> None:
    previous = list(_mask3(key, _MASK64))
    indices = range(len(flat) - 1, -1, -1) if reverse else range(len(flat))
    for index in indices:
        mask = _mask3(key, index)
        source = [int(flat[index, channel]) for channel in range(3)]
        output = [
            (source[channel] + previous[(channel + 1) % 3] + mask[channel]) & 0xFF
            for channel in range(3)
        ]
        flat[index, :3] = output
        previous = output


def _diffuse_inverse(flat: PixelArray, key: int, reverse: bool) -> None:
    previous = list(_mask3(key, _MASK64))
    indices = range(len(flat) - 1, -1, -1) if reverse else range(len(flat))
    for index in indices:
        mask = _mask3(key, index)
        encoded = [int(flat[index, channel]) for channel in range(3)]
        flat[index, :3] = [
            (encoded[channel] - previous[(channel + 1) % 3] - mask[channel]) & 0xFF
            for channel in range(3)
        ]
        previous = encoded


def _validate(pixels: PixelArray, rounds: int) -> ImageSpec:
    if rounds not in VALID_ROUNDS:
        raise AlgorithmError("轮数仅允许 1、5、10 或 20。")
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
        raise AlgorithmError("V1 仅支持 RGB 或 RGBA 像素矩阵。")
    spec = ImageSpec(pixels.shape[1], pixels.shape[0], "RGB" if pixels.shape[2] == 3 else "RGBA")
    validate_pixels(pixels, spec)
    return spec


def encrypt(
    pixels: PixelArray,
    seed: int,
    rounds: int,
    cancel: CancellationProbe | None = None,
) -> PixelArray:
    """Return a scrambled copy of a normalized RGB/RGBA matrix."""
    spec = _validate(pixels, rounds)
    words = _derive_words(spec, seed)
    output = pixels.copy(order="C")
    flat = output.reshape(-1, spec.channels)
    for round_index in range(rounds):
        _checkpoint(cancel)
        _lift_forward(flat, _round_key(words[0], round_index, 0x11))
        _checkpoint(cancel)
        _permute_forward(flat, _round_key(words[1], round_index, 0x22))
        _checkpoint(cancel)
        _diffuse_forward(flat, _round_key(words[2], round_index, 0x33), False)
        _diffuse_forward(flat, _round_key(words[3], round_index, 0x44), True)
    return output


def decrypt(
    pixels: PixelArray,
    seed: int,
    rounds: int,
    cancel: CancellationProbe | None = None,
) -> PixelArray:
    """Return the strict inverse of :func:`encrypt`."""
    spec = _validate(pixels, rounds)
    words = _derive_words(spec, seed)
    output = pixels.copy(order="C")
    flat = output.reshape(-1, spec.channels)
    for round_index in range(rounds - 1, -1, -1):
        _checkpoint(cancel)
        _diffuse_inverse(flat, _round_key(words[3], round_index, 0x44), True)
        _diffuse_inverse(flat, _round_key(words[2], round_index, 0x33), False)
        _checkpoint(cancel)
        _permute_inverse(flat, _round_key(words[1], round_index, 0x22))
        _checkpoint(cancel)
        _lift_inverse(flat, _round_key(words[0], round_index, 0x11))
    return output
