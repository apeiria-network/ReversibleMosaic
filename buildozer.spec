[app]
title = ReversibleMosaic
package.name = reversiblemosaic
package.domain = io.placeholder
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,json,md,ttf,ttc,txt
source.exclude_dirs = .git,.venv,.idea,tests,artifacts,build,bin,.buildozer,docs,vendor
source.include_patterns = main.py
version = 0.1.0
# Minimal probe requirements: verify Kivy + arm64 build first,
# then re-add kivymd/pillow/numpy/pyjnius one at a time.
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.api = 34
android.minapi = 26
android.ndk = 25b
android.archs = arm64-v8a
android.private_storage = True
android.accept_sdk_license = True
android.logcat_filters = *:S python:D SDL:D SDLActivity:D AndroidRuntime:E

# Use a locally-mirrored python-for-android checkout to avoid
# blocked github.com access; the working tree is at ~/vendor/python-for-android.
p4a.source_dir = /home/hydrogen/vendor/python-for-android

[buildozer]
log_level = 2
warn_on_root = 1
