# 脚本索引

工作区里的 `scripts/` 是构建与探测的辅助脚本集合。所有需要在 Ubuntu 环境跑的
脚本都以 `wsl_` 或 `probe_` 前缀开头；不带前缀的 Python 脚本可在 WSL 或
Windows 侧执行（但需要 `python-for-android` 可 import）。以下按用途分组，说明
每个脚本"做什么、什么时候用、跑在哪里"。

## 主构建

### `wsl_build_android.sh`
Buildozer 打包主入口。**在 WSL Ubuntu 里运行**（`wsl -d Ubuntu -- bash scripts/wsl_build_android.sh`
即可）。做的事情：
1. 杀掉遗留的 `buildozer` / `python-for-android` 进程（不影响自身 PID）。
2. **增量** rsync 把 Windows 侧源码同步进 `/home/hydrogen/src/ReversibleMosaic/`；`--exclude '.buildozer/'`
   保住之前编好的 CPython/SDL2/kivy 等原生库，改 py/spec 后重跑只花几分钟（而非 30 分钟从零编）。
3. 从 `~/.p4a-source-cache/` hard-link tarball 到 workspace 内 `packages/`，让
   p4a 全程跳过网络下载。
4. 设置每次调用生效的 `GIT_CONFIG_*` 环境变量，把 p4a recipe 里的
   `https://github.com/*` clone 重定向到 `https://ghfast.top/https://github.com/*`
   镜像；**不改用户 `~/.gitconfig`**。
5. `cd $WORKSPACE && exec buildozer android debug`，日志同时写到
   `/home/hydrogen/src/reversible-mosaic-build.log`。

改动此脚本时的注意事项：**不要**恢复 `rm -rf $WORKSPACE` —— 那会让每一轮打包都
从零重编 CPython；也不要修改用户全局 git 配置。

### `wsl_prefetch_p4a.sh`
一次性预取 p4a 需要的全部 tarball（hostpython3, jpeg, libffi, libwebp,
openssl, png, sdl2, sdl2_image, sdl2_mixer, sdl2_ttf, sqlite3, python3, kivy,
pyjnius, libthorvg, setuptools 等）到 `~/.p4a-source-cache/<recipe>/`，并写
`.mark-<basename>` 标记文件让 p4a 的 `download_if_necessary()` 直接跳过网络。
GitHub URL 走 `ghfast.top` 镜像；OpenSSL 官方站 301 重定向到 GitHub 也已直连
GitHub 发布 tarball 保持 basename 一致。

**首次搭建环境时跑一遍即可**，之后 `wsl_build_android.sh` 会自动从缓存
hard-link 到 workspace。如果 recipe 版本升级则需重跑。

## 网络探测（历史遗留，可选）

### `probe_mirrors.sh`
探测多个"GitHub 加速前置代理"域名的可达性（curl HEAD 到根路径拿 HTTP code）：
`mirror.ghproxy.com` / `ghfast.top` / `ghproxy.link` / `gh-proxy.com` /
`github.moeyy.xyz`。用于在 Windows hosts 劫持 github.com 的环境下选一个可用
镜像。当前使用的是 `ghfast.top`。

### `probe_git_mirrors.sh`
用几个不同的镜像 `git clone --depth 1` 一个小仓库（默认 `libsdl-org/jpeg`），
30 s 超时看是否能拉出内容。除了简单的 HTTP HEAD 之外，这里验证的是
"git+HTTPS smart protocol 是否也能穿过镜像"。

### `probe_direct_sources.sh`
探测 p4a 里非 GitHub 的直连 URL（如 `storage.googleapis.com` 上的 libwebp，
或者 `openssl.org` 官方 tarball），确认是否需要额外镜像。

## 调试专用

### `inspect_sdl2_image_submodules.sh`
读取 `sdl2_image` build tree 里所有 `.gitmodules` 文件，用于诊断
`SDL2_image` 递归 clone 出错时到底是哪个子模块。历史上帮助定位过
`libjxl → skcms → skia.googlesource.com`（这条链在 WSL 完全不可达；已用
p4a 就地补丁跳过 libjxl / libavif 子模块）。

### `enumerate_recipes.py`
遍历 `RECIPES` 列表，打印每个 p4a Recipe 的 `versioned_url` 与本地保存的
basename，方便预取脚本对齐 URL / 文件名。**必须在能 import
`pythonforandroid`** 的环境里跑（通常是 WSL 里的 `build-venv`）。

## 已知的运行约束

- 所有 `wsl_*.sh` 脚本假定 WSL 里已经准备好：
  - `~/.venvs/reversible-mosaic-build/`：装有 `buildozer` + `cython` 的 venv
  - `~/vendor/python-for-android/`：p4a 源码 checkout（buildozer.spec 通过
    `p4a.source_dir` 引用）
  - `~/.buildozer/android/platform/android-ndk-r25b/`：手动放置的 NDK r25b
- 不要在 Windows 侧直接跑 `.sh` —— 路径混用会出错。
- 不要在 `~/.gitconfig` 里配 GitHub 镜像；用 `wsl_build_android.sh` 里的
  `GIT_CONFIG_*` 环境变量方式（每次调用生效，不污染用户配置）。
