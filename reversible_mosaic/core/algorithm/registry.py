"""Algorithm registry and immutable public version descriptors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from reversible_mosaic.core.algorithm.contracts import CancellationProbe, PixelArray

Transform = Callable[[PixelArray, int, int, CancellationProbe | None], PixelArray]


@dataclass(frozen=True, slots=True)
class AlgorithmDescriptor:
    version: int
    display_name: str
    release_date: date | None
    encrypt: Transform
    decrypt: Transform


_REGISTRY: dict[int, AlgorithmDescriptor] = {}


def register(descriptor: AlgorithmDescriptor) -> None:
    if descriptor.version <= 0:
        raise ValueError("算法版本必须是正整数。")
    if descriptor.version in _REGISTRY:
        raise ValueError(f"算法 V{descriptor.version} 已注册。")
    _REGISTRY[descriptor.version] = descriptor


def get(version: int) -> AlgorithmDescriptor:
    try:
        return _REGISTRY[version]
    except KeyError as exc:
        raise ValueError(f"不支持算法 V{version}。") from exc


def supported_versions() -> tuple[AlgorithmDescriptor, ...]:
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY, reverse=True))


def latest() -> AlgorithmDescriptor:
    if not _REGISTRY:
        raise RuntimeError("尚未注册算法。")
    return _REGISTRY[max(_REGISTRY)]


_V1_IMPLEMENTATION: str = "reference"


def v1_implementation() -> str:
    """Return which V1 backend is currently registered: ``"cython"`` or ``"reference"``."""
    return _V1_IMPLEMENTATION


def _resolve_v1_transforms() -> tuple[Transform, Transform, str]:
    from reversible_mosaic.core.algorithm import reference_v1

    try:
        from reversible_mosaic.core.algorithm import optimized_v1
    except ImportError:
        return reference_v1.encrypt, reference_v1.decrypt, "reference"
    return optimized_v1.encrypt, optimized_v1.decrypt, "cython"


def _register_builtin_versions() -> None:
    global _V1_IMPLEMENTATION
    encrypt, decrypt, implementation = _resolve_v1_transforms()
    _V1_IMPLEMENTATION = implementation
    register(
        AlgorithmDescriptor(
            version=1,
            display_name="V1 (未发布)",
            release_date=None,
            encrypt=encrypt,
            decrypt=decrypt,
        )
    )


_register_builtin_versions()
