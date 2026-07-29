#!/usr/bin/env bash
# Build Linux x86_64 Cython .so + run visual review generator in WSL.
#
# Prereqs: Ubuntu-24.04 WSL with python3-venv (`apt install python3-venv`).
# This script owns the whole loop: it (re)creates the dev venv, ensures
# numpy / pillow / cython / setuptools are installed, rsyncs the workspace
# from Windows, compiles the Cython inner loops for the host, runs
# ``scripts/generate_visual_review_set.py`` (see ``--sources`` / ``--output``
# args), and rsyncs the outputs back to Windows.
#
# Do NOT ``cd /mnt/d/...`` before invoking a bare ``python3 -m venv "$X"`` —
# if $X is empty due to shell escaping quirks, venv will happily materialise
# in the current directory, and Windows won't be able to delete the resulting
# Linux symlinks. Always fully-qualify venv paths.
set -euo pipefail

VENV=/home/hydrogen/.venvs/reversible-mosaic-dev
VENV_PY="$VENV/bin/python"
VENV_PIP="$VENV/bin/pip"
WORKSPACE=/home/hydrogen/src/ReversibleMosaic
WIN_SOURCE=/mnt/d/python/python_projects/ReversibleMosaic

# 1. Ensure the dev venv exists with the deps we need.
if [ ! -x "$VENV_PY" ]; then
    python3 -m venv "$VENV"
fi
"$VENV_PIP" install --quiet --upgrade pip
"$VENV_PIP" install --quiet numpy pillow cython setuptools

# 2. Sync workspace from Windows.
rsync -a --delete \
    --exclude ".git/" --exclude ".venv/" --exclude ".buildozer/" \
    --exclude "build/" --exclude "bin/" --exclude "*.egg-info/" \
    --exclude "artifacts/visual_review/" \
    "$WIN_SOURCE/" "$WORKSPACE/"

cd "$WORKSPACE"

# 3. Compile Cython inner loops for the host (Linux x86_64) Python.
export REVERSIBLE_MOSAIC_BUILD_CYTHON=1
find reversible_mosaic/core/algorithm -name "v1.cpython-*-aarch64-*.so" -delete
"$VENV_PY" setup.py build_ext --inplace 2>&1 | tail -5

echo "--- backend check ---"
"$VENV_PY" -c "from reversible_mosaic.core.algorithm.registry import v1_implementation; print('backend =', v1_implementation())"

echo "--- running visual review generator ---"
PYTHONPATH="$WORKSPACE" "$VENV_PY" scripts/generate_visual_review_set.py "$@"

echo "--- copying outputs back to Windows workspace ---"
mkdir -p "$WIN_SOURCE/artifacts/visual_review"
rsync -a --delete \
    "$WORKSPACE/artifacts/visual_review/" \
    "$WIN_SOURCE/artifacts/visual_review/"

echo "done."
