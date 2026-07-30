# Android 构建基线（阶段 3 冻结）

> **文档版本**：0.1.0（阶段 3 冻结，2026-07-30）
> **对应 APK**：v15 debug (Stage 2b 收官) → v16 signed Release（Stage 3 Block 3 计划）
> **仅支持 ABI**：`arm64-v8a`；`armeabi-v7a` / `x86_64` 不在 MVP 范围。

本文档记录 MVP 第一次内部签名 Release 的**完整可复现构建基线**。任何工具链
版本变化都必须走"改动 → 复跑 build → 更新本文档 → 更新 [`docs/release-notes.md`](release-notes.md)"
四步同步，否则跨机器构建结果不一致。

---

## 1. 工具链冻结值

### 主机侧（构建机）

- **OS**：Windows 11 Home + WSL2 (Ubuntu 24.04)
- **Windows Python（PC dev / 测试）**：CPython 3.11.9
- **WSL Python（构建 harness）**：Python 3.12.3（系统自带，仅跑
  buildozer/p4a 编排，不进 APK）
- **构建 venv**：`~/.venvs/reversible-mosaic-build/`
- **Java**：OpenJDK 17（`sudo apt install openjdk-17-jdk`）
- **Android SDK**：Buildozer 自动下载到 `~/.buildozer/android/platform/android-sdk/`
- **Android NDK**：**r25b**（手动放置到 `~/.buildozer/android/platform/android-ndk-r25b/`；
  Buildozer 不会自动下载 r25b）
- **Android SDK build-tools**：36.0.0（Buildozer 拉的最新版）
- **Buildozer**：从 pip 安装到构建 venv
- **python-for-android**：本地 checkout 于 `~/vendor/python-for-android/`
  （main 分支，参考 `buildozer.spec::p4a.source_dir`）
- **Gradle wrapper**：8.14.3-all（从 `mirrors.cloud.tencent.com/gradle/` 镜像拉取，
  详见 [`docs/source-index.md`](source-index.md) § Android 打包障碍与已实施对策）

### APK 内运行时（p4a 打包）

- **Target Python**：**3.14**（p4a 交叉编译进 APK）
- **Kivy**：p4a 内置 recipe，随 python-for-android main 分支版本
- **PyJNIus**：p4a 内置 recipe
- **NumPy**：**2.3.0**（p4a 内置 recipe，我方本地 recipe override 加
  `<unordered_map>` include 补丁 —— 见 [`scripts/p4a_local_recipes/numpy/`](../scripts/p4a_local_recipes/numpy/)）
- **Pillow**：**11.3.0**（p4a 内置）
- **Cython**：**3.2.9**（宿主构建时使用；见下 § 3）
- **SDL2**：p4a 内置版本
- **libwebp / libjpeg / libpng / libffi / openssl / sqlite3**：p4a 内置 recipe

### Android 目标

| 项 | 值 |
|---|---:|
| `android.api` | 34 |
| `android.minapi` | 26 |
| `targetSdk` | 34（必须在正式发布日重新评估，AC-001 要求） |
| `android.archs` | `arm64-v8a` |
| `orientation` | `portrait`（锁定竖屏） |
| `android.permissions` | `WRITE_EXTERNAL_STORAGE`（`maxSdkVersion=28`），无其他权限 |
| Manifest 声明网络权限 | **无**（AC-016 飞行模式验收前置） |

---

## 2. PC 侧 dev 环境（跑 pytest / ruff / mypy）

- 见 [`requirements-dev.lock`](../requirements-dev.lock)。
- 关键版本：
  - CPython 3.11.9
  - NumPy 2.4.6 / Pillow 12.3.0（**注意与 APK 里的 2.3.0 / 11.3.0 不同步 —— 这
    是刻意的：PC 侧跑最新稳定版验证参考实现，APK 侧固定为 p4a 通过的版本**）
  - Cython 3.2.9（跟 APK 侧构建版本一致，保证 `.pyx` cythonize 输出等价）
  - pytest 9.1.1 / mypy 1.20.2 / ruff 0.16.0 / Hypothesis 6.161.2
  - Kivy 2.3.1 / KivyMD 1.2.0（PC 冒烟测试用；APK 侧走 p4a recipe 打包的 Kivy）

**Windows-only 依赖**（pywin32、pypiwin32、kivy-deps.*）不入 lock —— Linux CI
上装不上，且不影响 pytest / mypy / ruff 结果。

---

## 3. 构建入口与流程

> **⚠️ 打包必须走 [`scripts/wsl_build_android.sh`](../scripts/wsl_build_android.sh)。
> 不要手工 `cd /mnt/d/... && buildozer android debug`。**（原因见文件顶部注释；
> 简述：WSL2 的 9P/DrvFs 会把 p4a subprocess 卡成僵尸，实测挂死过 52 分钟。）

### 3.1 一次性准备（新机器 / 新 WSL）

1. WSL Ubuntu 24.04 里装 `sudo apt install openjdk-17-jdk python3-venv git rsync`。
2. 构建 venv：
   ```bash
   python3 -m venv ~/.venvs/reversible-mosaic-build
   source ~/.venvs/reversible-mosaic-build/bin/activate
   pip install buildozer cython
   ```
3. clone python-for-android 到 `~/vendor/python-for-android/`（main 分支），路径与
   `buildozer.spec::p4a.source_dir` 保持一致。
4. 手动下载 NDK r25b：
   `~/.buildozer/android/platform/android-ndk-r25b/`（Buildozer 会用这个目录）。
5. 首次预取 p4a tarballs：
   ```bash
   wsl -d Ubuntu -e bash /mnt/d/python/python_projects/ReversibleMosaic/scripts/wsl_prefetch_p4a.sh
   ```
   之后所有构建 hard-link 使用，全程不走网络。

### 3.2 增量构建（改代码后）

```powershell
# PowerShell / Windows shell
wsl -d Ubuntu -e bash /mnt/d/python/python_projects/ReversibleMosaic/scripts/wsl_build_android.sh
```

- 首次冷启动：25–30 分钟（编译 CPython 3.14 + SDL2 + libtvg + libwebp + kivy）
- 增量构建：3–5 分钟（改 py/spec 后）
- 产物：`~/src/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-debug.apk`

### 3.3 Cython 交叉编译

`scripts/wsl_build_android.sh` 会在 buildozer 之前调
[`scripts/wsl_build_v1_cython.sh`](../scripts/wsl_build_v1_cython.sh) 把
`reversible_mosaic/core/algorithm/v1.pyx` 交叉编译成
`v1.cpython-314-aarch64-linux-android.so`（cython 3.2.9 + NDK r25b clang-14 +
target Python 3.14 头）。buildozer 通过 `source.include_exts = ...,so,...`
把 loose `.so` 打进 APK。**首次冷启动时目标 Python 3.14 头文件还未生成，
第一次调用 Cython 脚本只做 `.pyx → .c` 一步返回 0；buildozer 建好 dist 后
需要再次运行 Cython 脚本得到 `.so`**。目前 `wsl_build_android.sh` 已
串联好两个阶段。

### 3.4 手工拷贝 APK 回 Windows 并打版本后缀

```bash
sha256sum ~/src/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-debug.apk
cp ~/src/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-debug.apk \
   /mnt/d/python/python_projects/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-debug-v16.apk
```

SHA-256 记录到 [`docs/release-notes.md`](release-notes.md) 的对应版本条目。

---

## 4. 签名策略

Stage 3 采用**内部自签 Release**（应用户决定，2026-07-30）：

- **applicationId**：保留探针值 `io.placeholder.reversiblemosaic`。正式面向
  公开用户发布前必须换成开发者自有域名反写的正式 ID。
- **keystore**：由用户在 WSL 本机用 `keytool` 生成，路径 `~/keys/reversiblemosaic.jks`，
  别名 `reversiblemosaic`，10000 天有效期。密钥文件与口令**不进入源码仓库、
  不发送给 AI**。
- **keystore 口令持久化**：写到 `buildozer.spec.local`（`.gitignore` 排除），
  buildozer 通过 `p4a.release_artifact` / signing config 读入。
- **发行说明必须写清**：Release APK 用的是内部自签 keystore，不能作为正式渠道
  发布身份使用，商用发布前需切换。

签名的具体 keytool / buildozer signing 步骤在 Stage 3 Block 3 落地时补
[`scripts/generate_release_keystore.sh`](../scripts/generate_release_keystore.sh)
与 `buildozer.spec.local` 模板；本文档届时追加 § 5"Release 签名执行"。

---

## 5. 已知构建障碍与对策（历史留档）

以下问题在 Stage 0–2 探针过程中遇到并已实施对策；升级 NDK / p4a / Buildozer
版本时如果不再需要，可以逐条移除。

- **Windows hosts 文件劫持 `github.com`**：`scripts/wsl_build_android.sh` 通过
  `GIT_CONFIG_COUNT/KEY_0/VALUE_0` 把 recipe 里的 `https://github.com/*` clone
  重定向到 `https://ghfast.top/https://github.com/*` 镜像。**每次调用生效，不改
  用户 `~/.gitconfig`**。
- **Gradle wrapper 从 `services.gradle.org` 下载失败**：改到 `mirrors.cloud.tencent.com/gradle/`；
  修改点在 p4a 的 `bootstraps/common/build/gradle/wrapper/gradle-wrapper.properties`
  模板以及已生成的 dist wrapper。
- **`sdl2_image → libjxl → skcms` 走 `skia.googlesource.com`**：完全不可达；
  已在 p4a `sdl2_image/__init__.py` 里跳过 libjxl 与 libavif 子模块。
- **`libthorvg` recipe 里 `libomp.so` glob 路径**：NDK r25b 布局是 `lib64/clang/...`，
  已改成 `lib*/clang/*/lib/linux/<arch>`。
- **NumPy 2.3.0 `unique.cpp` 缺 `<unordered_map>` include**：本地 recipe override
  在 [`scripts/p4a_local_recipes/numpy/`](../scripts/p4a_local_recipes/numpy/) 里
  自动应用 patch。

如果新一次冷启动构建报错，先看 [`docs/source-index.md`](source-index.md) § Android
打包障碍与已实施对策 —— 那里记录了每一条对策的详细来龙去脉。

---

## 6. 交付物清单（对应需求档 §16）

阶段 3 结束时必须交付：

1. 完整 Python/Kivy 工程源码（本仓库）+ 依赖锁定：[`requirements-dev.lock`](../requirements-dev.lock)、
   [`pyproject.toml`](../pyproject.toml)、[`buildozer.spec`](../buildozer.spec)
2. 算法设计 + 版本注册规则 + 固定向量：[`docs/algorithm-v1.md`](algorithm-v1.md)、
   [`tests/vectors/algorithm_v1.json`](../tests/vectors/algorithm_v1.json)
3. 自动化测试 + 性能测试 + 合成样本脚本 + 测试报告：
   [`tests/`](../tests/)、[`scripts/generate_visual_review_set.py`](../scripts/generate_visual_review_set.py)、
   [`docs/test-plan.md`](test-plan.md)
4. 测试集清单 + 来源 + 许可 + SHA-256：
   [`artifacts/visual_review/scorecard.md`](../artifacts/visual_review/scorecard.md)
5. Buildozer.spec + SDK/NDK 配置 + 构建文档：本文档 + 上面 § 3
6. **可安装的签名 Release APK**：Stage 3 Block 3 出 v16；SHA-256 与
   签名 fingerprint 记录到 [`docs/release-notes.md`](release-notes.md)
7. 用户教程（App 内置 TutorialScreen）+ 隐私说明（本 README 与需求档 §11）+
   第三方许可：[`docs/release-notes.md`](release-notes.md) § 第三方许可清单
