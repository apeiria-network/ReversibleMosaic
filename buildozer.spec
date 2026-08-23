# =============================================================================
# 打包入口必须是 scripts/wsl_build_android.sh，不要手工跑 `buildozer android debug`。
#
# 手工方式的陷阱：
#   1. Buildozer 会在当前工作目录建 .buildozer/。如果 cwd 是 /mnt/d/...，
#      整个构建落在 Windows 挂载盘上，WSL2 的 9P/DrvFs 会偶发把 p4a 起的
#      subprocess 卡成僵尸（52 分钟 0% CPU 那种），实测已挂死一次。
#   2. 会跳过 wsl_build_android.sh 里的 rsync 到 ~/src/ReversibleMosaic，
#      也跳过 p4a 包缓存 hard-link 和 github.com → ghfast.top 的 git 镜像。
#   3. 会跳过 wsl_build_v1_cython.sh 的交叉编译，得到一个没有 v1.so
#      的 fallback-only 包。
#   4. 会跳过 release 分支的 apksigner 签名封装（Stage 3 Block 3 Q1 决策 C）。
#
# 正确姿势（PowerShell / Windows shell 里，Stage 3 Block 3 起两参数都强制）：
#   wsl -d Ubuntu -e bash /mnt/d/python/python_projects/ReversibleMosaic/scripts/wsl_build_android.sh debug v18
#   wsl -d Ubuntu -e bash /mnt/d/python/python_projects/ReversibleMosaic/scripts/wsl_build_android.sh release v18
# 脚本自动加版本后缀、拷回 D:\...\bin\、打印 sha256sum；release 分支还会跑
# apksigner 签名 + verify + keytool -printcert 摘要。
# 详见 docs/source-index.md § 主构建 与 docs/build-android.md §3.2/§5.2。
# =============================================================================
[app]
title = ReversibleMosaic
package.name = reversiblemosaic
package.domain = io.placeholder
source.dir = .
source.include_exts = py,pyx,so,kv,png,jpg,jpeg,json,md,ttf,ttc,txt
source.exclude_dirs = .git,.venv,.idea,tests,artifacts,build,bin,.buildozer,docs,vendor,scripts
source.include_patterns = main.py,reversible_mosaic/core/algorithm/v1.so
version = 1.0.1
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

# Stage 2b: legacy save path on API 26-28 needs WRITE_EXTERNAL_STORAGE.
# API 29+ (scoped storage) does NOT need this permission for MediaStore inserts
# under the app's own RELATIVE_PATH, so cap it at maxSdkVersion=28. No network,
# location, or camera permissions requested (FR-TASK-007, §11.3).
android.permissions = (name=android.permission.WRITE_EXTERNAL_STORAGE;maxSdkVersion=28)

# Stage 3 Block 3: buildozer defaults `android release` to AAB (Google Play
# bundle format). AAB is Play Store-only — you can't `adb install` it and it
# can't be distributed as a plain download. AC-001 / AC-012 / AC-016 all
# require a directly-installable signed APK, so force APK output. Our target
# is a single ABI (arm64-v8a) with no resource splits, so AAB gains us
# nothing anyway.
android.release_artifact = apk

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
