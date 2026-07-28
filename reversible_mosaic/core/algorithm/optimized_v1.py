"""Cython-backed V1 that must be byte-identical to :mod:`reference_v1`.

The orchestration (round key derivation, cancellation checkpoints, alpha
handling) is imported from ``reference_v1`` so the two implementations cannot
drift; only the six inner loops are replaced with the ``nogil`` variants from
:mod:`reversible_mosaic.core.algorithm.v1`.

Import fails on platforms where the Cython artefact was not built (e.g. Windows
+ MSVC). Callers must handle :class:`ImportError` and fall back to
``reference_v1``.
"""

from __future__ import annotations

from reversible_mosaic.core.algorithm import v1 as _cy
from reversible_mosaic.core.algorithm.contracts import CancellationProbe, PixelArray
from reversible_mosaic.core.algorithm.reference_v1 import (
    _checkpoint,
    _derive_words,
    _round_key,
    _validate,
)

CYTHON_MODULE_PATH = _cy.__file__


def encrypt(
    pixels: PixelArray,
    seed: int,
    rounds: int,
    cancel: CancellationProbe | None = None,
) -> PixelArray:
    """Byte-identical accelerated variant of :func:`reference_v1.encrypt`."""
    spec = _validate(pixels, rounds)
    words = _derive_words(spec, seed)
    output = pixels.copy(order="C")
    flat = output.reshape(-1, spec.channels)
    for round_index in range(rounds):
        _checkpoint(cancel)
        _cy.lift_forward(flat, _round_key(words[0], round_index, 0x11))
        _checkpoint(cancel)
        _cy.permute_forward(flat, _round_key(words[1], round_index, 0x22))
        _checkpoint(cancel)
        _cy.diffuse_forward(flat, _round_key(words[2], round_index, 0x33), False)
        _cy.diffuse_forward(flat, _round_key(words[3], round_index, 0x44), True)
    return output


def decrypt(
    pixels: PixelArray,
    seed: int,
    rounds: int,
    cancel: CancellationProbe | None = None,
) -> PixelArray:
    """Byte-identical accelerated variant of :func:`reference_v1.decrypt`."""
    spec = _validate(pixels, rounds)
    words = _derive_words(spec, seed)
    output = pixels.copy(order="C")
    flat = output.reshape(-1, spec.channels)
    for round_index in range(rounds - 1, -1, -1):
        _checkpoint(cancel)
        _cy.diffuse_inverse(flat, _round_key(words[3], round_index, 0x44), True)
        _cy.diffuse_inverse(flat, _round_key(words[2], round_index, 0x33), False)
        _checkpoint(cancel)
        _cy.permute_inverse(flat, _round_key(words[1], round_index, 0x22))
        _checkpoint(cancel)
        _cy.lift_inverse(flat, _round_key(words[0], round_index, 0x11))
    return output
