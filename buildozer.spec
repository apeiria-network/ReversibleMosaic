[app]
title = ReversibleMosaic
package.name = reversiblemosaic
package.domain = io.placeholder
source.dir = .
source.include_exts = py,pyx,so,kv,png,jpg,jpeg,json,md,ttf,ttc,txt
source.exclude_dirs = .git,.venv,.idea,tests,artifacts,build,bin,.buildozer,docs,vendor,scripts
source.include_patterns = main.py
version = 0.1.0
# Stage 0 batch 2: keep runtime requirements minimal. Cython compilation of
# reversible_mosaic/core/algorithm/v1.pyx happens in a pre-buildozer step
# (scripts/wsl_build_v1_cython.sh), which drops the arm64 .so directly into
# the source tree so p4a bundles it as a loose file.
requirements = python3,kivy,pyjnius,numpy,pillow
orientation = portrait
fullscreen = 0
android.api = 34
android.minapi = 26
android.ndk = 25b
android.archs = arm64-v8a
android.private_storage = True
android.accept_sdk_license = True
android.logcat_filters = *:S python:D SDL:D SDLActivity:D AndroidRuntime:E

# Local recipe override for numpy 2.3.0 — adds a patch for the missing
# <unordered_map> include that Android NDK r25b clang-14 + libc++ trips over.
# Path is resolved inside the WSL workspace (matches wsl_build_android.sh rsync
# destination). Take precedence over p4a's built-in numpy recipe.
p4a.local_recipes = /home/hydrogen/src/ReversibleMosaic/scripts/p4a_local_recipes

# Use a locally-mirrored python-for-android checkout to avoid
# blocked github.com access; the working tree is at ~/vendor/python-for-android.
p4a.source_dir = /home/hydrogen/vendor/python-for-android

[buildozer]
log_level = 2
warn_on_root = 1
