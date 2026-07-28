#!/usr/bin/env bash
# Convenience script: run inside WSL to build the Android probe APK.
set -euo pipefail

MY_PID=$$
# Kill leftover buildozer/p4a processes but never this shell.
if command -v pgrep >/dev/null 2>&1; then
    for pid in $(pgrep -f "buildozer|python-for-android" || true); do
        [ "$pid" != "$MY_PID" ] && kill -9 "$pid" 2>/dev/null || true
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

# p4a's sdl2_image/sdl2_mixer/sdl2_ttf recipes and some others run `git clone
# https://github.com/...` for submodules during prebuild. github.com is DNS-
# hijacked on this host, so redirect all github.com clones to a public mirror
# via per-invocation git config env vars (no ~/.gitconfig touched).
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="url.https://ghfast.top/https://github.com/.insteadOf"
export GIT_CONFIG_VALUE_0="https://github.com/"

cd "$WORKSPACE"
: > "$LOG"
# Foreground; caller must background this script if desired.
exec buildozer android debug 2>&1 | tee -a "$LOG"
