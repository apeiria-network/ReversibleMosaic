# 技术探针记录

## PC 应用启动

- 环境：Windows 11，CPython 3.11.9。
- Kivy 2.3.1、KivyMD 1.2.0 可安装。
- `main.py` 成功创建 SDL2/OpenGL 窗口并进入应用主循环；8 秒后由 smoke-test timeout 主动终止，无启动异常。
- KivyMD 1.2.0 在运行时提示版本已弃用。Android recipe 可用性验证前暂不切换未正式发布的 2.0 master；该项列入依赖风险。

## 参考算法性能

Windows CPython 纯 Python、RGBA、单轮：

| 尺寸 | 耗时 | 吞吐 |
|---|---:|---:|
| 64×64 | 0.0368s | 111,212 px/s |
| 128×128 | 0.1435s | 114,180 px/s |
| 256×256 | 0.5799s | 113,008 px/s |

线性外推 1920×1080 单轮约 18 秒、20 轮约 6 分钟，纯 Python 明确不能满足需求目标。参考实现仅作为规范 oracle；必须用 Cython/C 级循环优化后再评估，属于计划内风险而非当前阻塞。

## Android 构建环境

- WSL2 Ubuntu 可用，Python 3.12.3。
- WSL 当前缺少 JDK、Buildozer 和 Android SDK/NDK。
- 自动安装依赖时 `apt-get update` 长时间停滞；终止后，清理 apt 锁并重试会修改共享 WSL 包管理状态，当前自动权限策略不允许执行。
- 下一步需用户在 WSL 终端完成一次人工工具链安装，之后我继续构建 arm64 探针 APK。

## 阶段 0 v5 真机自检 (2026-07-28)

- **APK**：`bin/reversiblemosaic-0.1.0-arm64-v8a-debug-v5.apk`
- **SHA-256**：`5d6a0d9c6e5a9623b7e6518b25eb77d5a1f69041ce5f1a80e3e972eb9bb4c04c`
- **大小**：34.1 MiB
- **ABI**：arm64-v8a；minSdk 26；`targetSdk 34`
- **requirements**：`python3,kivy,pyjnius,numpy,pillow`（Stage 0 batch 1，Cython/v1_optimized 走 v6）
- **测试设备档次**：约 8 GB RAM 中高端 arm64 手机 / Android（具体型号 SoC 未公开，正式发布前需绑定"约定设备"到本记录以便 AC-PERF 引用）

### 探针结果

| 探针 | 结果 |
|---|---|
| pyjnius | ✅ `autoclass OK; package=io.placeholder.reversiblemosaic` |
| numpy | ✅ `numpy=2.3.0, arr.shape=(4, 4, 4), dtype=uint8` |
| pillow | ✅ `PIL=11.3.0, 4x4 RGBA PNG=88B round-trip OK` |
| V1 参考实现 4x4 RGBA α=0 | ✅ rounds 1/5/20 全部逐字节相等（**透明 RGB 零差异达标**）|
| V1 Cython 优化 | ⏳ `NOT_BUILT`（v5 未打 Cython，v6 目标 PASS）|

### 性能扫描（真机 256×256 RGB, 参考实现, 5 次取中位数）

| rounds | median | p95 | peak_rss |
|---:|---:|---:|---:|
| 1 | 1.311 s | 1.359 s | 275 MiB |
| 10 | 12.787 s | 12.909 s | 275 MiB |
| 20 | 37.625 s | 49.099 s | 275 MiB |

**总耗时 260.9 s，实现 = reference-v1。**

### 外推到 1920×1080 (纯 Python 参考实现)

256×256 = 65 536 px，1920×1080 = 2 073 600 px，比例 **31.6×**。按线性外推：

| rounds | 外推真机耗时 | AC-PERF 目标 | 倍数 |
|---:|---:|---:|---:|
| 1 | ≈ 41 s | ≤ 3 s | **13.6× 超标** |
| 10 | ≈ 6.7 min | ≤ 18 s | **22× 超标** |
| 20 | ≈ 20 min | ≤ 35 s | **34× 超标** |

**结论**：纯 Python 参考实现绝对无法满足 AC-PERF。阶段 1 必须完成 Cython v1_optimized 到 encrypt/decrypt pipeline 的**完整**接入（不仅仅是探针加载），并把参考实现降级为规范 oracle。

### 阶段 0 退出标准对表

| 退出条件 | 状态 |
|---|---|
| arm64 APK 可安装、启动 | ✅ v5 已安装、启动、UI 可读 |
| 关键依赖可稳定打包 | ✅ pyjnius / numpy / pillow 三个原生 .so import 通过 |
| 透明 RGB 零差异 on-device | ✅ 4×4 RGBA α=0 rounds 1/5/20 逐字节相等 |
| 主线程可响应 | ✅ 自检屏 5 项探针 + 性能扫描 worker 后台跑期间 UI 不卡 |
| 平台链路可行 | ✅ Kivy + SDL2 + libtvg + numpy + Pillow + pyjnius arm64 完整链路成立 |
| Cython v1_optimized 打包并 on-device 可加载 | ✅ v6 完成（详见下节）|

**阶段 0 达成度：6/6 完成，可以转向阶段 1。**

### 构建路径已知隐患

**numpy 2.3.0 编译需要手工补丁**：`numpy/_core/src/multiarray/unique.cpp` 使用 `std::unordered_map` 但只 include 了 `<unordered_set>`；GCC/glibc 有传递包含，Android NDK r25b clang-14 + libc++ 没有，导致 build 报 `no template named 'unordered_map' in namespace 'std'`。

- **v5 处理**：`scripts/wsl_patch_numpy_include.sh`（幂等，重跑安全）——手工触发一次
- **v6 处理**：抬到 p4a 的本地 recipe 覆盖 `scripts/p4a_local_recipes/numpy/`，
  内置 `patches = ["patches/numpy_unordered_map_include.patch"]`，
  `buildozer.spec` 里配 `p4a.local_recipes` 指向它 —— 未来清 `.buildozer/`
  重建时 p4a 自动应用，不需要人工干预

## 阶段 0 v6 真机自检 (2026-07-28)

- **APK**：`bin/reversiblemosaic-0.1.0-arm64-v8a-debug-v6.apk`
- **SHA-256**：`928e478aeb0939bb8396c5d24e6cb89cc25c90dd94da713d217a3c34fbbdf7fd`
- **大小**：34.1 MiB（比 v5 多 172 KiB = Cython `.so`）
- **requirements**：`python3,kivy,pyjnius,numpy,pillow`（不加 `cython` 到 p4a runtime；
  见"打包路径变化"）
- **测试设备档次**：约 8 GB RAM 中高端 arm64 手机 / Android（与 v5 同机器）

### 探针结果

所有 5 项探针 PASS。关键变化：

| 探针 | v5 | v6 |
|---|---|---|
| V1 Cython 优化 | ⏳ `NOT_BUILT: No module named 'reversible_mosaic.core.algorithm.v1'` | ✅ `Cython 模块加载 OK; lift_forward/lift_inverse 复原一致` |

其他 4 项 (`pyjnius` / `numpy` / `pillow` / V1 参考实现) 全部保持 PASS，无回归。

### 性能扫描（256×256 RGB, 5 次取中位数，与 v5 同实现）

| rounds | v5 median | v6 median | v5 p95 | v6 p95 |
|---:|---:|---:|---:|---:|
| 1 | 1.311 s | 1.328 s | 1.359 s | 1.357 s |
| 10 | 12.787 s | 13.009 s | 12.909 s | 15.735 s |
| 20 | 37.625 s | 25.626 s | 49.099 s | 25.648 s |

峰值 RSS 均 275–283 MiB。20 轮 v5→v6 快 32% 是**热身/调度抖动**，不是 Cython 加速
—— **性能扫描目前仍跑 `reference_v1` 纯 Python 参考实现**，Cython inner loops
只是被"装到 APK 里"了。真正的 AC-PERF 数字要等阶段 1 把 Cython 接入
encrypt/decrypt pipeline 后重新基准。

### 打包路径变化 (v5 → v6)

| 项 | v5 | v6 |
|---|---|---|
| Cython 集成方式 | 未打包 | **预交叉编译 `.pyx` → arm64 `.so`**，作为 loose file 打进 APK |
| 交叉编译工具链 | — | Cython 3.x（build venv 装的）+ NDK r25b `aarch64-linux-android26-clang` + `.buildozer` 下已建的 target Python 3.14 头 / `libpython3.14.so` |
| 触发时机 | — | `wsl_build_android.sh` 在 buildozer 之前调 `scripts/wsl_build_v1_cython.sh` |
| 落盘位置 | — | `reversible_mosaic/core/algorithm/v1.cpython-314-aarch64-linux-android.so`（172 KiB） |
| APK 内路径 | — | `assets/private.tar` 内 `reversible_mosaic/core/algorithm/v1.cpython-*.so` |
| numpy 补丁持久化 | 手工脚本兜底 | 抬到 `scripts/p4a_local_recipes/numpy/patches/*.patch`，`buildozer.spec` 配 `p4a.local_recipes` |

**为什么不用 `p4a.setup_py = 1`**：试过一轮，p4a 的 setup.py 模式假设 app 已被
预安装到 target site-packages 里，但 p4a 本身**不会自动跑 pip install**；结果
APK 里只有 `main.pyc` 一个文件，`reversible_mosaic/` 整个模块都没进包。回退到
"loose file + 预交叉编译 `.so`"是最简单可靠的路径。`setup.py` 保留在项目根供
PC dev `python setup.py build_ext --inplace` 时用（Windows 上因缺 `__uint128_t`
自动跳过）。

