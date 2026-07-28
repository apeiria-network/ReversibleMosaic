"""Setuptools build hook for compiling Cython inner loops.

Metadata (name, version, dependencies) lives in ``pyproject.toml``; this file
only exists so p4a (with ``p4a.setup_py = 1`` in ``buildozer.spec``) and any
local ``python setup.py build_ext --inplace`` invocation can cross-compile the
V1 inner loops into a Python extension on the target platform.

The embedded C helper uses ``__uint128_t`` which is a GCC/clang extension.
Windows/MSVC has no 128-bit integer type, so this file skips Cython compilation
under MSVC and falls back to the pure-Python ``reference_v1`` at runtime.
"""

from __future__ import annotations

import os
import sys

from setuptools import setup

try:
    from Cython.Build import cythonize
except ImportError:  # pragma: no cover - build-system deps guarantee Cython
    cythonize = None


CYTHON_MODULES = [
    "reversible_mosaic/core/algorithm/v1.pyx",
]


def _should_build_cython() -> bool:
    if cythonize is None:
        return False
    # Force override for CI / debugging.
    override = os.environ.get("REVERSIBLE_MOSAIC_BUILD_CYTHON")
    if override is not None:
        return override != "0"
    # Skip on MSVC (Windows) — the .pyx uses __uint128_t which MSVC lacks.
    if sys.platform == "win32":
        return False
    return True


ext_modules = (
    cythonize(
        CYTHON_MODULES,
        language_level=3,
        compiler_directives={
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
        },
    )
    if _should_build_cython()
    else []
)


setup(ext_modules=ext_modules)
