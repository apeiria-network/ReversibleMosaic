# Android 构建基线（阶段 0 草案）

## 当前环境检查

- Windows 项目虚拟环境：CPython 3.11.9。
- WSL2：Ubuntu，Python 3.12.3。
- WSL 当前未安装 JDK、Buildozer、Android SDK/NDK。
- P0 ABI：仅 `arm64-v8a`；最低 API 26。

## 预定工具链

`buildozer.spec` 当前是探针配置，不是发布冻结值：

- Kivy 2.3.1
- KivyMD 1.2.0
- python-for-android（首次成功构建后锁定 commit）
- Android API 35 / min API 26
- NDK 27c
- Python 3.11.9
- NumPy 2.0.2 / Pillow 11.1.0 / PyJNIus 1.6.1

任何依赖因 recipe 不兼容需要调整时，先记录实际构建输出。正式发布时按渠道政策更新 targetSdk 并重新执行完整测试。

## WSL 构建原则

- 工程复制到 WSL 的 Linux 文件系统构建，避免 `/mnt/d` I/O 和权限问题。
- SDK/NDK 与 Gradle 缓存不进入仓库。
- 发布签名密钥、别名和口令不进入源码或命令历史。
- APK 构建成功后记录 SHA-256、工具版本和 Manifest 权限。

## 人工协助节点

当探针 APK 生成后，如开发环境没有可用 ADB 真机，将请求用户：

1. 在 Android 8.0+ arm64 设备安装 APK；
2. 记录 Android 版本、设备 RAM 和安装结果；
3. 运行首页/教程并反馈截图；
4. 后续探针页完成透明 PNG 往返、取消和 MediaStore 保存测试。
