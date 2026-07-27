#!/usr/bin/env bash
set -u
root=/home/hydrogen/src/ReversibleMosaic/.buildozer/android/platform/build-arm64-v8a/build/bootstrap_builds/sdl2/jni/SDL2_image
if [ ! -d "$root" ]; then
  echo "SDL2_image build dir not found: $root"
  exit 1
fi
find "$root" -maxdepth 4 -name ".gitmodules" | while read -r f; do
  echo "=== $f ==="
  cat "$f"
  echo
done
