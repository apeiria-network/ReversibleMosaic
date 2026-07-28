#!/usr/bin/env bash
# Cross-compile reversible_mosaic/core/algorithm/v1.pyx to an arm64
# Python 3.14 extension module, then drop the resulting `.so` directly into
# the workspace's source tree so p4a bundles it as a loose file.
#
# Runs INSIDE the WSL workspace (i.e., $WORKSPACE = /home/hydrogen/src/ReversibleMosaic/),
# not the Windows mount. Called from wsl_build_android.sh after rsync + prefetch
# but before `buildozer android debug`.
#
# Requires that p4a has already built the arm64 Python 3.14 target once (i.e.,
# the v5 dist exists on disk). If the target Python is missing, this script
# still runs a Cython .c generation step but skips the clang link — the calling
# script should then invoke buildozer once to build the dist and re-run this
# script.
set -euo pipefail

WORKSPACE="/home/hydrogen/src/ReversibleMosaic"
BUILD_VENV="/home/hydrogen/.venvs/reversible-mosaic-build"
NDK_ROOT="${NDK_ROOT:-$HOME/.buildozer/android/platform/android-ndk-r25b}"
NDK_API="${NDK_API:-26}"
PY_ROOT="$WORKSPACE/.buildozer/android/platform/build-arm64-v8a/build/other_builds/python3/arm64-v8a__ndk_target_26/python3/android-build/android-root"
PY_INCLUDE="$PY_ROOT/include/python3.14"
PY_LIBDIR="$PY_ROOT/lib"

CYTHON_BIN="$BUILD_VENV/bin/cython"
CLANG="$NDK_ROOT/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android${NDK_API}-clang"

SRC="$WORKSPACE/reversible_mosaic/core/algorithm/v1.pyx"
GEN_C="$WORKSPACE/reversible_mosaic/core/algorithm/v1.c"
OUT_SO="$WORKSPACE/reversible_mosaic/core/algorithm/v1.cpython-314-aarch64-linux-android.so"

if [ ! -x "$CYTHON_BIN" ]; then
    echo "[cython] no cython in $BUILD_VENV; installing Cython 3.x..."
    "$BUILD_VENV/bin/pip" install --quiet "Cython>=3.0,<4"
fi

echo "[cython] cythonize $SRC -> $GEN_C"
"$CYTHON_BIN" -3 --line-directives -o "$GEN_C" "$SRC"

if [ ! -f "$PY_INCLUDE/Python.h" ]; then
    echo "[cython] target Python 3.14 headers missing; skipping clang link."
    echo "[cython] Expected: $PY_INCLUDE/Python.h"
    echo "[cython] Run buildozer once first to build the arm64 dist, then rerun."
    exit 0
fi

if [ ! -x "$CLANG" ]; then
    echo "[cython] NDK clang not found at $CLANG"
    exit 1
fi

echo "[cython] compile $GEN_C -> $OUT_SO"
"$CLANG" \
    -shared -fPIC \
    -Wno-unreachable-code \
    -Wno-unused-function \
    -Wno-implicit-function-declaration \
    -O2 \
    -DNDEBUG \
    -I"$PY_INCLUDE" \
    -L"$PY_LIBDIR" \
    -o "$OUT_SO" \
    "$GEN_C" \
    -lpython3.14 \
    -llog

echo "[cython] built $(basename "$OUT_SO") ($(stat -c '%s' "$OUT_SO") bytes)"
file "$OUT_SO" || true
