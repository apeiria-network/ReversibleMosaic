"""Cython-backed V1 that must be byte-identical to :mod:`reference_v1`.

The orchestration (round key derivation, cancellation checkpoints, radius
computation) is imported from ``reference_v1`` so the two implementations
cannot drift; only the inner neighbourhood-swap loop is replaced with the
``nogil`` variant from :mod:`reversible_mosaic.core.algorithm.v1`.

Import fails on platforms where the Cython artefact was not built (e.g. Windows
+ MSVC). Callers must handle :class:`ImportError` and fall back to
``reference_v1``.
"""

from __future__ import annotations

from reversible_mosaic.core.algorithm import v1 as _cy
from reversible_mosaic.core.algorithm.contracts import CancellationProbe, PixelArray
from reversible_mosaic.core.algorithm.reference_v1 import (
    _SWAP_DOMAIN,
    _checkpoint,
    _derive_words,
    _radius_for,
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
    radius = _radius_for(spec.width, spec.height)
    for round_index in range(rounds):
        _checkpoint(cancel)
        _cy.neighborhood_swap_forward(
            output, _round_key(words[1], round_index, _SWAP_DOMAIN), radius
        )
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
    radius = _radius_for(spec.width, spec.height)
    for round_index in range(rounds - 1, -1, -1):
        _checkpoint(cancel)
        _cy.neighborhood_swap_inverse(
            output, _round_key(words[1], round_index, _SWAP_DOMAIN), radius
        )
    return output
