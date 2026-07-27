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
