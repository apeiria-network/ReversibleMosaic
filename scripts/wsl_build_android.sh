#!/usr/bin/env bash
# Convenience script: run inside WSL to build the Android APK (debug or release).
#
# Usage:
#   wsl_build_android.sh              # debug build (default)
#   wsl_build_android.sh debug        # explicit debug
#   wsl_build_android.sh release      # release build (requires buildozer.spec.local
#                                       with android.release_keystore + passwords;
#                                       generate via scripts/generate_release_keystore.sh)
set -euo pipefail

BUILD_MODE="${1:-debug}"
case "$BUILD_MODE" in
    debug|release) ;;
    *)
        echo "[error] unknown build mode: $BUILD_MODE (expected: debug|release)" >&2
        exit 2
        ;;
esac

MY_PID=$$
# Kill leftover buildozer/p4a processes but never this shell or our caller.
# NOTE: match the actual executables/module names, NOT the bare word
# "buildozer" — otherwise any parent shell whose command line mentions the
# word (e.g., log file paths like /tmp/buildozer_v16.log) gets kill -9'd
# too, taking this script down with it (exit 9). Learned the hard way
# during the v15→v16 build cycle.
if command -v pgrep >/dev/null 2>&1; then
    for pid in $(pgrep -f 'bin/buildozer|pythonforandroid\.toolchain|python-for-android' || true); do
        [ "$pid" != "$MY_PID" ] && [ "$pid" != "$PPID" ] && kill -9 "$pid" 2>/dev/null || true
    done
fi

WORKSPACE="/home/hydrogen/src/ReversibleMosaic"
BUILD_VENV="/home/hydrogen/.venvs/reversible-mosaic-build"
LOG="/home/hydrogen/src/reversible-mosaic-build.log"
P4A_CACHE="${P4A_CACHE:-$HOME/.p4a-source-cache}"
P4A_PACKAGES_DIR="$WORKSPACE/.buildozer/android/platform/build-arm64-v8a/packages"

# Incremental sync from Windows into WSL: preserve $WORKSPACE/.buildozer/ so
# recipes/other_builds (CPython/openssl/SDL2/kivy) don't rebuild from scratch.
# `--delete` still trims files removed from Windows, but rsync excludes both
# from transfer AND deletion, so .buildozer/ stays intact.
mkdir -p "$WORKSPACE"
rsync -a --delete \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude ".idea/" \
    --exclude ".mypy_cache/" \
    --exclude ".pytest_cache/" \
    --exclude ".ruff_cache/" \
    --exclude ".hypothesis/" \
    --exclude "build/" \
    --exclude "bin/" \
    --exclude ".buildozer/" \
    --exclude "keys/" \
    --exclude "*.egg-info/" \
    /mnt/d/python/python_projects/ReversibleMosaic/ "$WORKSPACE/"

# Seed the workspace-local p4a packages cache from the stable prefetched copy so
# python-for-android skips network downloads entirely.
if [ -d "$P4A_CACHE" ]; then
    mkdir -p "$P4A_PACKAGES_DIR"
    for recipe_dir in "$P4A_CACHE"/*/; do
        recipe_name="$(basename "$recipe_dir")"
        dest="$P4A_PACKAGES_DIR/$recipe_name"
        mkdir -p "$dest"
        # Hard-link tarballs and marker files; overwrite if already present.
        cp -a -f -l "$recipe_dir"/. "$dest"/
    done
    echo "[prefetch] seeded $(ls "$P4A_PACKAGES_DIR" | wc -l) recipes from $P4A_CACHE"
fi

export PATH="$BUILD_VENV/bin:$PATH"
export VIRTUAL_ENV="$BUILD_VENV"
unset PYTHONHOME

# Cross-compile the V1 Cython inner loops for arm64 Python 3.14 into a `.so`
# and drop it into the source tree so buildozer bundles it as a loose file.
# On the very first (clean) build the target Python doesn't exist yet, so
# this script emits the .c file only and exits 0 — buildozer will then build
# the dist and a subsequent rerun of wsl_build_android.sh will finish the
# clang link. Safe to run every build (idempotent).
bash "$WORKSPACE/scripts/wsl_build_v1_cython.sh" || {
    echo "[wsl_build_android] v1 cython step failed; will retry after buildozer builds the dist"
}

# p4a's sdl2_image/sdl2_mixer/sdl2_ttf recipes and some others run `git clone
# https://github.com/...` for submodules during prebuild. github.com is DNS-
# hijacked on this host, so redirect all github.com clones to a public mirror
# via per-invocation git config env vars (no ~/.gitconfig touched).
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="url.https://ghfast.top/https://github.com/.insteadOf"
export GIT_CONFIG_VALUE_0="https://github.com/"

cd "$WORKSPACE"
: > "$LOG"

# For release builds we require the signing config to exist. Buildozer would
# otherwise silently produce an unsigned APK that Android refuses to install.
# spec.local is generated on the Windows side by generate_release_keystore.sh,
# so the rsync above has already brought it into $WORKSPACE.
if [ "$BUILD_MODE" = "release" ]; then
    SPEC_LOCAL="$WORKSPACE/buildozer.spec.local"
    if [ ! -f "$SPEC_LOCAL" ]; then
        echo "[error] release build requested but $SPEC_LOCAL missing." >&2
        echo "        Run scripts/generate_release_keystore.sh first." >&2
        exit 3
    fi
    echo "[wsl_build_android] release build using signing config $SPEC_LOCAL"
fi

# Foreground; caller must background this script if desired.
exec buildozer android "$BUILD_MODE" 2>&1 | tee -a "$LOG"
