"""P1 candidate: optional bounded colour transform for V1.

**Not wired into production V1.** V1 as frozen (2026-07-29) is pure spatial
permutation (see :mod:`reversible_mosaic.core.algorithm.reference_v1`); pixel
values are only moved, never modified, so the colour palette is preserved
identically between input and encrypted output.

This module preserves the lift + diffuse primitives from the pre-freeze V1
draft as a reference implementation for a **future P1 "enhanced privacy mode"**.
If that mode ships, callers would:

1. Apply :func:`lift_forward` after :func:`neighborhood_swap_forward`
2. Apply :func:`diffuse_forward` for cross-pixel colour spreading
3. Reverse the order for decrypt

The functions here are **byte-compatible with the pre-freeze V1 draft** (which
had lift → permute → diffuse_fwd → diffuse_rev as the four sub-ops per round),
so any P1 wiring can reuse them without redesigning the math.

**Reversibility**: each function has a strict inverse below it. Every step is
a modulo-256 additive lift with per-pixel PRF masks, so subtract-then-add
recovers the original byte exactly.

**Alpha**: never read, never written. RGBA is treated as RGB + carry-along
Alpha; lift and diffuse only touch channels 0-2.
"""

from __future__ import annotations

from reversible_mosaic.core.algorithm.contracts import PixelArray

_MASK64 = (1 << 64) - 1


def _splitmix64(value: int) -> int:
    """Local copy so this module does not depend on ``reference_v1`` internals."""
    value = (value + 0x9E3779B97F4A7C15) & _MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
    return (value ^ (value >> 31)) & _MASK64


def _mask3(key: int, index: int) -> tuple[int, int, int]:
    value = _splitmix64(key ^ index)
    return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF


def lift_forward(flat: PixelArray, key: int) -> None:
    """Per-pixel RGB triangular lifting; Alpha untouched.

    Reversible; :func:`lift_inverse` undoes this exactly for any RGB values.
    """
    for index, pixel in enumerate(flat):
        m0, m1, m2 = _mask3(key, index)
        r, g, b = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
        r = (r + 3 * g + 5 * b + m0) & 0xFF
        g = (g + 5 * b + 7 * r + m1) & 0xFF
        b = (b + 7 * r + 3 * g + m2) & 0xFF
        pixel[0], pixel[1], pixel[2] = r, g, b


def lift_inverse(flat: PixelArray, key: int) -> None:
    for index, pixel in enumerate(flat):
        m0, m1, m2 = _mask3(key, index)
        r, g, b = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
        b = (b - 7 * r - 3 * g - m2) & 0xFF
        g = (g - 5 * b - 7 * r - m1) & 0xFF
        r = (r - 3 * g - 5 * b - m0) & 0xFF
        pixel[0], pixel[1], pixel[2] = r, g, b


def diffuse_forward(flat: PixelArray, key: int, reverse: bool) -> None:
    """Per-pixel modular-add diffusion chain; Alpha untouched.

    ``reverse=True`` scans from tail to head so the two directions cover the
    whole image with a single-step feedback chain.
    """
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


def diffuse_inverse(flat: PixelArray, key: int, reverse: bool) -> None:
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


__all__ = [
    "diffuse_forward",
    "diffuse_inverse",
    "lift_forward",
    "lift_inverse",
]
