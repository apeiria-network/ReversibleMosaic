#!/usr/bin/env bash
# Patch numpy 2.3.0's unique.cpp to add missing #include <unordered_map>.
# Android NDK r25b clang-14 + libc++ does not transitively include the map
# header the way GCC/glibc does, so numpy's build fails without this patch.
# Idempotent: skips if already patched.
set -euo pipefail

F="/home/hydrogen/src/ReversibleMosaic/.buildozer/android/platform/build-arm64-v8a/build/other_builds/numpy/arm64-v8a__ndk_target_26/numpy/numpy/_core/src/multiarray/unique.cpp"

if [ ! -f "$F" ]; then
  echo "unique.cpp not found at $F; nothing to patch"
  exit 0
fi

if grep -q "^#include <unordered_map>" "$F"; then
  echo "already patched"
  exit 0
fi

sed -i '/^#include <unordered_set>/a #include <unordered_map>' "$F"
echo "patched:"
grep -n "^#include <unordered" "$F"
