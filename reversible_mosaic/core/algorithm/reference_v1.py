"""Reference implementation of the V1 pixel protocol.

V1 uses **pure reversible spatial permutation**: each round performs a single
forward-scan pass in which every pixel derives a partner index via SplitMix64
constrained to a modular (2R+1)x(2R+1) window and swaps in-place when the
partner index is higher (canonical direction). Iterating in the reverse
direction during decode replays the same swap sequence and undoes the
composed permutation exactly.

Key properties:

- **Palette-preserving**: pixel values are only moved, never modified. The
  encrypted output has the exact same multiset of pixels as the input.
- **Alpha-preserving**: RGB and Alpha channels move together as a unit; Alpha
  values are never touched by arithmetic.
- **Reversible**: forward∘inverse = identity for any legal input.
- **Deterministic**: same (input, seed, rounds) always produces the same
  bytes; no ``hash()``, no thread-local state.

The byte-level behavior in this module becomes immutable only after the V1
specification and fixed vectors are explicitly marked frozen. Cython
acceleration (:mod:`reversible_mosaic.core.algorithm.v1`) must be byte-identical
to this reference.

Colour-transform sub-ops (lift + diffuse) that appeared in the pre-freeze V1
draft have been extracted to
:mod:`reversible_mosaic.core.algorithm.color_transform` as a P1 candidate;
they are **not** called from production ``encrypt`` / ``decrypt``.
"""

from __future__ import annotations

import hashlib
import struct

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

# Neighbourhood radius R = max(RADIUS_MIN, min(W, H) // RADIUS_DIVISOR).
# The formula gives ~6% of the image's short edge on realistic photos and
# floors at 8 px for very small images so single-pixel/tiny inputs still
# permute meaningfully. See docs/algorithm-v1.md for the design rationale.
_RADIUS_MIN = 8
_RADIUS_DIVISOR = 32

# Domain tag applied to the neighbourhood-swap round key. Kept identical to
# the pre-freeze draft's permute stage so vector regeneration is a byte-level
# translation from the old encoding.
_SWAP_DOMAIN = 0x22


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & _MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
    return (value ^ (value >> 31)) & _MASK64


def _derive_words(spec: ImageSpec, seed: int) -> tuple[int, int, int, int]:
    """Derive 4 x 64-bit master words from (seed, dims, mode).

    Four words are returned even though V1 only reads ``words[1]`` for the
    swap-round-key derivation. The extra three slots are reserved for future
    P1 wiring (colour transform, secondary shufflers) without needing a
    schema bump on the derivation.
    """
    if not 0 <= seed <= 9_999_999_999:
        raise AlgorithmError("扰动种子超出 V1 允许范围。")
    mode_id = 3 if spec.mode == "RGB" else 4
    payload = _DOMAIN + struct.pack("<QIIIB", seed, spec.width, spec.height, 1, mode_id)
    return struct.unpack("<QQQQ", hashlib.sha256(payload).digest())


def _round_key(word: int, round_index: int, domain: int) -> int:
    return _splitmix64(word ^ (round_index * 0xD1342543DE82EF95) ^ domain)


def _checkpoint(cancel: CancellationProbe | None) -> None:
    if cancel is not None and cancel():
        raise CancellationRequested("处理已取消。")


def _radius_for(width: int, height: int) -> int:
    """Adaptive neighbourhood radius: R = max(8, min(W, H) // 32)."""
    return max(_RADIUS_MIN, min(width, height) // _RADIUS_DIVISOR)


def _neighborhood_swap_forward(
    pixels: PixelArray, key: int, radius: int
) -> None:
    """Forward-scan neighbourhood swap in place.

    For each pixel ``i = y*W + x`` in scan order, derive a partner
    ``(yj, xj)`` uniformly in the modular ``(2R+1)^2`` window around
    ``(y, x)``. Swap when ``j > i`` so each unordered pair fires exactly
    once from its lower-indexed member. RGBA rows move as a unit — Alpha
    is never separated from its RGB.
    """
    height, width, _ = pixels.shape
    denom = 2 * radius + 1
    for y in range(height):
        for x in range(width):
            i = y * width + x
            offset = _splitmix64(key ^ i)
            dy = ((offset >> 32) & _MASK64) % denom - radius
            dx = (offset & 0xFFFFFFFF) % denom - radius
            yj = (y + dy) % height
            xj = (x + dx) % width
            j = yj * width + xj
            if j > i:
                tmp = pixels[y, x].copy()
                pixels[y, x] = pixels[yj, xj]
                pixels[yj, xj] = tmp


def _neighborhood_swap_inverse(
    pixels: PixelArray, key: int, radius: int
) -> None:
    """Undo :func:`_neighborhood_swap_forward` by walking indices in reverse."""
    height, width, _ = pixels.shape
    denom = 2 * radius + 1
    for y in range(height - 1, -1, -1):
        for x in range(width - 1, -1, -1):
            i = y * width + x
            offset = _splitmix64(key ^ i)
            dy = ((offset >> 32) & _MASK64) % denom - radius
            dx = (offset & 0xFFFFFFFF) % denom - radius
            yj = (y + dy) % height
            xj = (x + dx) % width
            j = yj * width + xj
            if j > i:
                tmp = pixels[y, x].copy()
                pixels[y, x] = pixels[yj, xj]
                pixels[yj, xj] = tmp


def _validate(pixels: PixelArray, rounds: int) -> ImageSpec:
    if rounds not in VALID_ROUNDS:
        allowed = "、".join(str(n) for n in sorted(VALID_ROUNDS))
        raise AlgorithmError(f"轮数仅允许 {allowed}。")
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
    """Return a spatially-scrambled copy of a normalized RGB/RGBA matrix."""
    spec = _validate(pixels, rounds)
    words = _derive_words(spec, seed)
    output = pixels.copy(order="C")
    radius = _radius_for(spec.width, spec.height)
    for round_index in range(rounds):
        _checkpoint(cancel)
        _neighborhood_swap_forward(
            output, _round_key(words[1], round_index, _SWAP_DOMAIN), radius
        )
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
    radius = _radius_for(spec.width, spec.height)
    for round_index in range(rounds - 1, -1, -1):
        _checkpoint(cancel)
        _neighborhood_swap_inverse(
            output, _round_key(words[1], round_index, _SWAP_DOMAIN), radius
        )
    return output
