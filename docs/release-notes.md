# ReversibleMosaic 发行说明（v0.1.0 MVP 内部签名 Release）

> **版本**：0.1.0
> **发布类型**：**内部签名 Release**（不面向公开渠道，applicationId 尚未定型）
> **发布日期**：Stage 3 Block 3 结束时补上
> **发布主体**：暂无（内部自签 keystore）
> **对应需求档**：[`requirements_product_v1.md`](../requirements_product_v1.md) V2.0（2026-07-24）
> **对应算法冻结**：V1（[`docs/algorithm-v1.md`](algorithm-v1.md) 状态 FROZEN，2026-07-30）

---

## 1. 版本身份与限制（重要）

- **applicationId**：`io.placeholder.reversiblemosaic` —— 探针占位符，
  **不是**开发者正式身份。
- **签名 keystore**：由构建者在本机 `keytool -genkey` 生成的自签 keystore，
  仅用于满足 Android 安装/升级要求；**不能作为正式渠道发布身份使用**。
- **正式面向公开用户发布前必须完成**：
  1. 换成开发者自有域名反写的正式 applicationId（此项**永久不可再改**，
     一旦发布就绑定给这个 ID 所有历史用户）。
  2. 用同一个正式 keystore 重签名（**同一 keystore 从此不可丢**，丢了 =
     同 applicationId 永远发不出升级）。
  3. 决定发布主体名（个人开发者姓名 / 组织名）并写进 keystore CN/O 字段。
  4. 决定发布渠道（Google Play / 华为 / 直接分发 / GitHub Releases）。
  5. 重新按 §12.3 原条款组织 3 名独立检查者复跑视觉验收（当前用的是
     §12.3 单人 MVP 偏差条款）。

---

## 2. 已完成的核心功能

### 图片处理

- Android 8.0（API 26）+ arm64-v8a 单张图片本地打码/恢复。
- 静态 8 位 RGB/RGBA PNG 与普通 8 位 RGB JPEG（含 EXIF Orientation 1–8 修正）。
- 输入尺寸上限：50 MP，边长 12288 px，宽高比 64:1（覆盖 48-50MP 主流手机相机主档）。
- 轮数 `{2, 5, 15, 30}`，默认 5；分享代码 1–10 位十进制数字，默认 `500000`；
  可随机生成 6 位（100000-999999，避开默认值）。
- V1 算法：纯位置置换（palette-preserving）；半径 R=max(8, min(W,H)/32)；
  RGBA 四通道整体作为像素单位移动，Alpha 从不单独修改，透明像素中的 RGB
  完整保留。

### Android 集成

- Photo Picker（Intent.ACTION_GET_CONTENT）拉起系统相册选图，PC 侧回退到
  Kivy FileChooser。
- MediaStore 保存到 `Pictures/ReversibleMosaic`（API 29+ IS_PENDING 事务 +
  SHA-256 复读校验；API 26-28 insert-write-verify-scanner），任何失败自动
  删除 pending 行不留半文件。
- Intent.ACTION_VIEW / ACTION_SEND 打开与分享，subject 使用 App 通用标识，
  不含分享代码。
- Android 13+ ClipboardManager 敏感标记（ClipDescription.EXTRA_IS_SENSITIVE=true）。
- 输出文件命名：`<原名>_mosaic.png` / `<原名>_reversal_mosaic.png`（重名 `_1/_2`）；
  原名从 ContentResolver 的 DISPLAY_NAME 查询获得。
- App 启动时自动清理孤儿 IS_PENDING 行（FR-TASK-006）。

### 性能

- 1920×1080 RGB 图片、Cython 加速内循环，30 轮真机中位数约 1.53 s（v7 debug
  APK 数据外推，AC-PERF 目标 52 s 的 34× 余量）；峰值 RSS ~275 MiB。
- V1 Cython `.so` 交叉编译进 APK；PC 侧走 Python 参考实现兜底。

### 隐私

- **无网络权限**：Manifest 未申请 INTERNET / ACCESS_NETWORK_STATE 等，飞行
  模式下核心功能可用。
- 无广告、无遥测、无历史/最近图片 URI/分享代码持久化。
- 分享代码不进入 PNG 元数据、文件名、日志或分享文字。
- 权限：仅 `WRITE_EXTERNAL_STORAGE`（`maxSdkVersion=28`），API 29+ 无任何权限。

---

## 3. 已知限制与非目标

以下是 MVP 明确不支持的能力，用户教程和 App 首页均有说明：

- 16 位 PNG、灰度 / 灰度 Alpha / 调色板 PNG 不作为 P0 承诺（可能自动展开为
  RGB/RGBA，但不保证格式保真）。
- CMYK / YCCK JPEG、ICC 色彩管理一致性。
- WebP、GIF、动画图片、RAW 格式。
- 批量、视频、云同步、账号、历史图片列表、分享代码托管或找回。
- **对截图、裁剪、缩放、滤镜、有损压缩、转码、像素编辑结果的无损恢复**。
- **密码学机密性、真实性、完整性、抗暴力枚举保证**。这是可逆视觉混淆，
  不是加密。

---

## 4. 已知问题

- **旗舰机 108/200 MP 直出照片**：`domain/limits.py::MAX_PIXELS = 50M` 会拒绝，
  提示图片过大。用户可先在系统相册压缩到 50 MP 以下。
- **极端全景（>3:1 且 >30 MP）**：MAX_EDGE=12288 会先拒。同上处理。
- **Kivy FileChooser 兜底路径**：Photo Picker Intent 失败时切到 Kivy 内置
  FileChooser；此路径在 Android 上不如系统相册流畅，但功能可用。
- **进程被系统杀死后不恢复处理中任务**：FR-TASK-006 明确不承诺，App 启动会
  清理私有临时数据。
- **分享代码遗失无法找回**：需求档 FR-ENC-009 明规；用户教程有强提示。

---

## 5. 版本历史

### v0.1.0（MVP 首次内部 Release，Stage 3）

- Stage 0：探针 APK v1–v6，验证 arm64-v8a 打包链路（PyJNIus、NumPy、Pillow、
  Cython、透明 RGBA 零差异往返）。
- Stage 1：V1 算法冻结、Cython 加速接入、AC-PERF 34× 余量通过、apeiria-network
  单人视觉验收 80 项通过（§12.3 单人 MVP 偏差路径）。
- Stage 2a：PC 侧 UI 打通（EncodeScreen / DecodeScreen / ProgressScreen /
  ResultScreen）。
- Stage 2b：Android 集成（MediaStore、Photo Picker、敏感剪贴板、`_mosaic` 命名）。
- Stage 3：稳定性 fuzz 扩展、依赖版本固化、内部签名 Release APK、AC 全表验收。

**APK SHA-256 记录**：

| APK 版本 | 大小 | 文件 SHA-256 | 签名方案 | 签名主体 | 证书 SHA-256 fingerprint |
|---|---:|---|---|---|---|
| v15 debug (Stage 2b) | ~34 MiB | *(见 [`bin/`](../bin/) 目录 sha256sum)* | debug keystore (v1+v2) | Android debug | — |
| v17 debug (Stage 3) | ~34 MiB | *(见 [`bin/`](../bin/) 目录 sha256sum)* | debug keystore (v1+v2) | Android debug | — |
| **v17 signed Release** | **31.6 MiB** (33,115,120 B) | `546dc561005b2a02745d6ec10bdfdcc4cd46a33cd4c26f435e208a49919b0394` | v2 + v3 (Android 8.0+ 兼容) | `CN=Apeiria-network, C=CN` | `54c1bbbf48f34aae46225a3ef4f332852a9b8f3ac42930d47132a1b41d6c91a7` |

**v17 signed Release 补充信息**：
- 签名日期：2026-07-31（Stage 3 Block 3）
- Key 算法：RSA-2048
- Key alias：`reversiblemosaic`
- 签名 keystore：`<项目>/keys/reversiblemosaic.jks`（内部自签，`.gitignore` 已排除；WSL 侧不留副本，`wsl_build_android.sh` 的 rsync 已加 `--exclude "keys/"`）
- 证书 SHA-1 fingerprint：`46a3154a05571f416a0f4cd7ea795c19a65079fa`
- 未启用签名方案：v1 (JAR)、v3.1、v3.2、v4、SourceStamp —— 均为可选，Android 8.0+ 装机仅需 v2 或 v3 之一。
- **签名产物路径**：`bin/reversiblemosaic-0.1.0-arm64-v8a-release-v17.apk`（Windows 侧）与
  `~/src/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-release.apk`（WSL 侧，无版本后缀）
- **签名流程说明**：buildozer 在当前配置下产出 `*-release-unsigned.apk`（即使
  `buildozer.spec.local` 里有 signing config），需要额外用 Android SDK 的
  `apksigner` 手工签名。命令详见 [`docs/build-android.md`](build-android.md) § 5.2。

---

## 6. 第三方组件与许可清单

本 App 打包的开源依赖及其许可协议如下。所有许可原文将随交付物一并提供
（`reversible_mosaic/assets/fonts/LICENSE.txt` + Stage 3 Block 3 补齐的
`THIRD_PARTY_LICENSES/` 目录）。

### 6.1 APK 运行时组件

| 组件 | 版本 | 许可 | 用途 |
|---|---|---|---|
| CPython | 3.14 | PSF-2.0 | Android 侧 Python 解释器（p4a 交叉编译） |
| Kivy | p4a recipe main | MIT | UI 框架 |
| SDL2 | p4a recipe | Zlib | Kivy 底层图形/输入 |
| PyJNIus | p4a recipe | MIT | Python ↔ Java JNI 桥 |
| NumPy | 2.3.0 | BSD-3-Clause | 像素矩阵运算 |
| Pillow | 11.3.0 | HPND | PNG / JPEG 解码 + EXIF 处理 |
| Cython | 3.2.9 | Apache-2.0 | V1 算法内循环加速（生成 `.so` 打包进 APK） |
| libwebp | p4a recipe | BSD-3-Clause | Pillow WebP 后端（未启用但打进） |
| libjpeg-turbo | p4a recipe | BSD-3-Clause + zlib | JPEG 解码 |
| libpng | p4a recipe | libpng license | PNG 解码 |
| libffi | p4a recipe | MIT | ctypes 支持 |
| openssl | p4a recipe | Apache-2.0（v3+） | Python `ssl` / `hashlib` 后端 |
| sqlite3 | p4a recipe | Public Domain | Python `sqlite3` 后端（未使用但打进） |
| WenQuanYi Micro Hei（wqy-microhei.ttc） | 0.2.0-beta | **Apache 2.0** 或 **GPL-3+ with Font exception**（双许可） | UI 中文/Latin 字体，5.2 MiB |

### 6.2 PC dev 环境组件（不进 APK）

见 [`requirements-dev.lock`](../requirements-dev.lock)。主要许可：

- pytest, Hypothesis：MIT
- mypy：MIT
- ruff：MIT
- KivyMD（PC 冒烟）：MIT

### 6.3 构建工具（不进 APK）

- Buildozer：MIT
- python-for-android：MIT
- Android SDK / NDK：Android SDK License
- OpenJDK 17：GPLv2 with Classpath Exception

---

## 7. 用户教程要点

App 内置 TutorialScreen 已涵盖以下要点（§6.3）；发行说明再列一遍供检索：

1. **操作步骤**：首页 → 打码 / 恢复 → 选图 → 调轮数与分享代码 → 开始 → 保存到相册。
2. **参数匹配**：恢复必须用与打码时**相同的**算法版本、轮数与分享代码。
3. **传播限制**：只有本 App 未修改的原始打码 PNG 才能逐像素恢复；社交平台/
   截图/裁剪/滤镜后无法还原。
4. **剪贴板风险**：分享代码复制到剪贴板可能被其他 App 读取；Android 13+ 系统
   会遮盖敏感剪贴板预览，其他版本请谨慎。
5. **分享代码遗失**：App 不保存分享代码，也不提供找回；请你自己抄下来。
6. **非密码学安全**：这是可逆视觉混淆，不是加密；不要用于对抗有能力的攻击者。

---

## 8. 支持与反馈

- 项目仓库：（用户自行维护，不在本发行说明范围内）。
- Bug / Feature 请求：通过项目仓库 issue 提交。

---

**⚠️ 再次强调**：本 APK 使用**内部自签 keystore**，**applicationId 是探针占位**。
在你决定"正式面向公开用户发布"之前，请务必先按 § 1 五步走完发布身份切换，
否则会给你未来的正式发布带来永久性障碍（applicationId 不可改、keystore 不可换）。
