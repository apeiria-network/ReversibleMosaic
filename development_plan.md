# ReversibleMosaic 开发计划

## Context

项目当前只有 [requirements_product_v1.md](../../../python/python_projects/ReversibleMosaic/requirements_product_v1.md)，尚无源码、构建配置、测试资产或 Git 仓库。目标是从零搭建一个 Android 8.0+、全离线、单图、逐像素可逆的视觉混淆 MVP，并最终形成可安装 APK、源码、固定向量、测试和构建文档。

已确认：V1 算法由本项目设计并冻结；不存在历史兼容负担，但代码从 V1 起采用版本注册结构；优先按需求指定的 Python + Kivy/KivyMD + Buildozer 实现，技术验证不达标时可提出切换方案；本轮按阶段推进到可运行 MVP，遇到协议、性能或平台集成的严重阻塞时暂停并提供实测数据后询问。

主要风险是：V1 数学定义尚未冻结、Python/Android 对 12MP 与 20 轮的性能、RGBA 透明像素隐藏 RGB 的保真、受限 PNG 元数据解析、API 26–28/29+ MediaStore 差异，以及发布性能设备和正式签名信息尚未确定。

## 计划导出与协作约定

- 计划获批进入执行后，第一步将本计划原样导出到工作区根目录 `development_plan.md`，作为项目内可持续更新的执行基线；后续阶段结论、风险、实测结果和人工验收记录同步写入该文件。
- 标记为 **【人工协助】** 的节点更适合由用户在真实设备、视觉判断、系统授权或发布身份方面完成。到达节点时我会暂停，说明操作步骤、预期结果和需要反馈的证据，再请求用户协助；无需用户提前操作。
- 标记为 **【联合】** 的节点由我先完成自动化或构建准备，再请用户进行最小必要的人工操作。我会根据反馈继续，不把未执行的人工步骤声称为已通过。
- 一般编码、自动测试、样本生成、静态检查、PC 基准和文档更新由我完成；只有需求不清、严重技术阻塞或下述人工节点才暂停。

## 推荐架构

- **应用层**：Python 3 + Kivy/KivyMD，ScreenManager/MVVM 风格；页面只消费不可变 UI 状态，不直接处理全尺寸像素。
- **领域层**：分享代码、版本注册、任务状态机、错误分级、资源预算均为无 Android 依赖的纯 Python 模块。
- **核心层**：NumPy 保存紧密 RGB/RGBA 数组；纯 Python 参考算法负责规范与固定向量，Cython 优化核心负责逐像素置换/扩散并释放 GIL。PC 与 Android 调用同一 V1 规则。
- **文件层**：Pillow 负责受控解码/编码；在 Pillow 前自建有界 PNG/JPEG 头部与 chunk/segment 扫描，先完成格式、尺寸、文本、EXIF/ICC 和资源预算检查，避免解压炸弹和无界元数据读取。
- **平台层**：PyJNIus 封装 Photo Picker/SAF、ContentResolver、MediaStore、Intent、剪贴板；业务层只依赖 gateway 接口，PC 测试使用 fake。
- **并发**：单活动任务 + 工作线程；Cython 长循环按固定粒度检查取消；Kivy Clock 仅在主线程更新 Widget、纹理和 Intent。
- **技术闸门**：先构建 arm64 APK 探针，验证 NumPy/Pillow/Cython/PyJNIus、透明 RGB、URI、取消和 MediaStore。若在时间盒内不能满足要求，则暂停并提交测量结果及 Kotlin/Rust 迁移建议，不私自维护双技术栈。

## V1 算法冻结方案

1. 输入契约为行优先、8 位 RGB/RGBA、宽高、算法版本、轮数和规范化种子；空代码映射 500000，非空仅接受 1–10 位 ASCII 数字并按整数去前导零。
2. 使用带域分离标签的 SHA-256 固定次数派生版本/尺寸/模式/种子参数；所有序列化显式规定字节序，不使用 `hash()`，派生成本和扫描次数不随种子数值变化。
3. 每轮固定执行：
   - RGB 三角 lifting 混合：模 256 加法，逐步更新，逆向按相反通道顺序减法；Alpha 不读取、不参与混合。
   - 全像素 Fisher–Yates 置换：`j_i` 由可随机访问的计数器 PRF 与无偏乘法映射得到；RGB/RGBA 以完整像素交换。正向 `N-1→1`，逆向重新生成相同索引并按 `1→N-1` 交换，不保存置换表。
   - 正向与反向 RGB 扩散：各使用独立域参数和反馈链，逆变换按严格相反步骤执行；Alpha 仅随空间置换移动，数值不改。
4. 逆过程按轮次倒序执行扩散逆、置换逆、lifting 逆；覆盖 1×1、1×N、N×1、奇数尺寸和 Alpha=0 非零 RGB。
5. 冻结前对 1–20 轮做周期抽样，对固定图集记录像素变化率、相邻相关性和边缘相似度，并组织需求规定的视觉复核；阈值以实测报告冻结，未通过则修改原型而不是发布。
6. 冻结 `algorithm-v1.md`、参数派生、固定向量和跨平台结果；冻结后任何像素差异都只能新增 V2，不能修改 V1。

## 关键目录与文件

- `pyproject.toml`、`requirements*.lock`：PC/Android 依赖与工具版本。
- `main.py`、`reversible_mosaic/app.py`、`reversible_mosaic/ui/*.kv`：应用入口、主题、首页、打码、恢复、教程、结果页。
- `reversible_mosaic/domain/share_code.py`、`algorithm_registry.py`、`task_state.py`、`limits.py`：纯领域规则。
- `reversible_mosaic/core/algorithm/reference_v1.py`、`v1.pyx`、`pipeline.py`：参考算法、优化实现和处理管线。
- `reversible_mosaic/io/probe.py`、`normalize.py`、`png_metadata.py`、`png_writer.py`：安全探测、规范化、协议和编码复读。
- `reversible_mosaic/android/picker.py`、`media_store.py`、`intents.py`、`clipboard.py`：Android 适配器。
- `tests/unit/`、`tests/property/`、`tests/vectors/`、`tests/adversarial/`、`tests/android/`：测试分层。
- `docs/algorithm-v1.md`、`docs/architecture.md`、`docs/build-android.md`、`docs/test-plan.md`：冻结规范和交付文档。
- `buildozer.spec`、`recipes/`、`.github/workflows/`：arm64 构建、自定义 Cython recipe 与 CI。

## 分阶段执行

### 0. 基线与可行性探针

- 初始化 Git、忽略规则、Python 工程、锁定工具链、lint/type/test 配置和需求追踪表。
- 建最小 Kivy Android APK，贯通 PyJNIus、NumPy/Pillow/Cython、私有缓存、PNG 透明 RGB 往返、取消及 API 26/29+ MediaStore 冒烟链路。
- 用 1920×1080 RGB/RGBA 原型扫描评估 1/10/20 轮时间和峰值内存。
- **【联合】arm64 探针安装**：我生成 APK 和校验值；如本环境无法直连设备，请用户在 Android 8.0+ arm64 真机安装，反馈安装结果、Android 版本及崩溃/权限截图。
- **退出标准**：arm64 APK 可安装；关键依赖可稳定打包；透明 RGB 零差异；主线程可响应；平台链路可行。否则暂停汇报并请求技术栈决策。

### 1. 核心算法与文件协议

- 实现分享代码规则、资源预算、安全头部探测、JPEG Orientation 1–8、RGB/RGBA 规范化、元数据严格解析/序列化和 PNG 复读校验。
- 实现 V1 参考/优化正逆算法、注册表、固定向量、合成样本、性质测试、周期/质量指标和泄露扫描。
- **【人工协助】视觉扰乱初审**：我输出固定原图与 1/5/10/20 轮结果及指标表，请用户按“主体、人脸、文字是否可直接辨认”记录判断；正式发布前仍需 3 名检查者完成冻结验收。
- **退出标准**：AC-004/005/006/008/010/011/014 相关 PC 测试通过；PC 端 AC-015 指标冻结；参考与优化实现逐字节一致；删除元数据仍可恢复。

### 2. Android MVP 应用

- 实现首次边界说明、首页、打码、恢复、教程、进度/取消、候选预览、双重离开提醒和可操作参数控件。
- 完成 Photo Picker 优先/SAF 回退、URI 有界复制、私有缓存、任务状态机和线程安全 UI 回调。
- 完成 API 29+ pending 事务、API 26–28 兼容保存/回滚、查看/分享 URI 授权及敏感剪贴板提示。
- **【联合】真机端到端验收**：我提供 APK、测试图片和逐步清单；请用户在可用真机上执行选图、授权拒绝/重试、保存、相册查看、系统分享、切后台和取消，并反馈截图或录屏及设备信息。
- **退出标准**：真机跑通选图→规范化→打码→保存→分享→恢复；失败/取消可重试；无历史、代码或 URI 持久化；Manifest 无网络等额外权限。

### 3. 稳定性、性能与交付

- 执行恶意输入、元数据 fuzz、生命周期、并发取消、低存储、权限拒绝、API 26/28/29/当前版、深浅色/大字体和飞行模式测试。
- 在约定 8GB arm64 真机用签名 Release APK 连续 5 次采集中位数/P95、分阶段耗时和峰值内存；完成 3 人视觉验收。
- 固化 Buildozer/python-for-android/SDK/NDK/JDK/Cython/依赖版本，生成第三方许可、测试报告、发行说明与签名 APK。
- **【人工协助】设备与视觉验收**：请用户指定或提供约 8GB arm64 性能机，并协调 3 名检查者；我提供固定样本、表单和判定规则，用户回传原始记录。
- **【人工协助】发布身份与签名**：到 Release 阶段再请用户确认正式应用名、永久 applicationId、发布渠道/主体，并在本机生成或提供签名配置；密钥和口令不发送给我、不写入仓库，我只提供安全操作步骤并验证签名结果。
- **【联合】安装与飞行模式验收**：我交付候选 APK 和检查清单，请用户在目标真机完成安装升级、飞行模式全流程、系统分享接收方和相册可见性检查。
- **退出标准**：需求 AC-001～017 与 AC-PERF 有可追踪证据；构建可复现；APK SHA-256、签名和安装结果已记录。

## 验证策略

- **单元/表驱动**：分享代码、轮数、版本、状态迁移、限制计算、错误文案、元数据 schema。
- **性质测试**：任意合法小矩阵/模式/种子/轮数满足 `decrypt(encrypt(x)) == x`；确定性、前导零等价、尺寸/模式/Alpha 不变。
- **固定向量**：RGB/RGBA、边缘尺寸、规定种子和 1/5/10/20 轮；PC 与 arm64 Android 比较完整像素和关键阶段摘要。
- **编解码/安全**：Orientation 1–8、透明隐藏 RGB、截断/CRC/炸弹/伪造尺寸/异常 EXIF、重复或超限文本、未来 schema/算法。
- **泄露检查**：扫描 PNG、文件名、日志、异常、偏好、缓存命名和分享 Intent，确认无分享代码和完整 URI。
- **端到端**：API 26–28 与 29+ 保存事务、失败回滚、查看/分享权限、切后台、进程回收、取消后再处理、飞行模式。

## 执行时暂停条件与默认值

出现以下情况立即暂停询问：V1 无法同时达到可逆与质量阈值；冻结后需改变像素规则；透明 RGB 无法保留；优化后性能仍明显超标或 12MP 内存不可控；API 26–28 需要超出需求的权限/流程；依赖许可证或漏洞阻断；需要改变资源阈值；需要增加网络/遥测；进入正式发布但 applicationId、发布主体、签名或性能设备尚未确定。

可直接采用的非阻塞默认值：简体中文、竖屏、跟随系统深浅色、保存至 `Pictures/ReversibleMosaic`、预览最长边 1600px、临时 applicationId、默认 5 轮/500000、启动清理超过 24 小时的私有临时文件、不保存历史/URI/分享代码。正式发布前再确认永久 applicationId、应用名称、签名主体、发布渠道和性能验收设备。

## 执行进度日志（滚动更新）

### 阶段 0 – 基线与可行性探针
- Git 与 pyproject 就绪，ruff/mypy 严格模式绿灯，pytest 全绿（110 个单元/性质/固定向量/恶意输入/协调器测试）。
- Kivy/KivyMD 应用外壳（首页、教程、Placeholder）可在 PC 启动。
- Cython 优化模块草稿在 Windows 已编译，等 Android 打包通过后再切 registry。
- 领域层：分享代码、资源预算、任务状态机、取消 token、进度回调、任务 view model 均已具备单元测试。
- IO 层：安全 PNG chunk 扫描、JPEG 有界 preflight、EXIF 1–8、元数据严格解析/复读、恶意输入拒绝、方向固定向量全部通过。
- 核心：V1 参考实现 + Cython 加速草稿 + `process_image` pipeline + `TaskCoordinator` worker 线程封装（含取消/失败/成功/进度分发）。

### Android 打包障碍与已实施对策
- **Windows hosts 文件劫持** `github.com`、`api.github.com`、多个 `*.github.*` 到 `127.0.0.1`，WSL 走 Windows DNS 也被拉黑；已通过 GitHub 公共加速镜像 `ghfast.top` 绕行，不再要求你解开 hosts。
- p4a 15 个源码 tarball（hostpython3/python3/kivy/sdl2/…/openssl）已一次性预取到 `~/.p4a-source-cache/<recipe>/<file>` + `.mark-<file>` 标记文件；`scripts/wsl_build_android.sh` 会在每次 build 前把缓存 hardlink 进 workspace 内 `packages/`，让 p4a 全程跳过网络下载。
- p4a `sdl2_image` 在 prebuild 递归 clone 子模块；已通过 `GIT_CONFIG_COUNT/KEY_0/VALUE_0` 让 `https://github.com/*` 全部走 `ghfast.top` 代理，不改用户 `~/.gitconfig`。
- `SDL2_image → libjxl → skcms` 走 `skia.googlesource.com`，该域名在本 WSL 完全不可达；已就地补丁 p4a 的 `sdl2_image/__init__.py` 跳过 `libjxl` 与 `libavif` 子模块（二者在 SDL2_image Android.mk 中默认 `SUPPORT_JXL/AVIF ?= false`，跳过不影响功能）。
- OpenSSL 官网 301 重定向到 GitHub 也被劫持；预取脚本已直接使用 GitHub 上的 openssl 发布 tarball，保持 basename 一致以便 p4a 命中缓存。
- p4a `libthorvg` recipe 在 install 阶段用 `lib/clang/*/lib/linux/<arch>` glob 定位 `libomp.so`，但 NDK r25b 布局是 `lib64/clang/...`，导致 `IndexError`；已就地把 recipe 里的 glob 改成 `lib*/clang/*/lib/linux/<arch>`，同时兼容旧/新 NDK 布局。
- Gradle wrapper 从 `services.gradle.org` 下载 `gradle-8.14.3-all.zip` 时 GFW 直接 `Connection refused`；已把 p4a `bootstraps/common/build/gradle/wrapper/gradle-wrapper.properties` 模板与已生成的 dist wrapper 都改到 `https://mirrors.cloud.tencent.com/gradle/gradle-8.14.3-all.zip`，wrapper 自动重新计算 hash 并从腾讯云拉取。

### 阶段 0 探针 APK 迭代记录
- **v1 → v2**：v1 APK 只有 `python3,kivy`，但 `app.py` import 了 `kivymd.app.MDApp` → 启动即 `ImportError` 闪退。把 UI 从 `MDApp/MDBoxLayout/MDLabel/MDRaisedButton/MDScreenManager` 全量降级为纯 Kivy `App/BoxLayout/Label/Button/ScreenManager`，同时放宽 `android.logcat_filters = *:S python:D SDL:D SDLActivity:D AndroidRuntime:E`。
- **v2 → v3**：v2 装完不闪退，UI 布局正确，但所有中文渲染为方框（tofu）。原因是 Kivy 默认 Roboto 不含 CJK。第一次尝试用 `DroidSansFallbackFull.ttf`（Android AOSP 原字体，Apache-2.0）—— 3.9 MB，全 CJK。
- **v3 → v4**：v3 中文正常，但 **"ReversibleMosaic"（纯 Latin）**、数字 `1.` `2.`、ASCII 分号斜杠逗号仍为方框 —— 因为 DroidSansFallback 是 Android 系统"回退字体"，故意只覆盖 CJK 表意汉字。改换 **WenQuanYi Micro Hei（文泉驿微米黑）5.2 MB TTC**，Apache-2.0 或 GPL-3+ with Font exception 双许可，Latin + Simplified Chinese 均覆盖；从阿里云 Ubuntu 镜像抓 `.deb` 包 `dpkg-deb -x` 解压得到，不走 `sudo apt install`。
- **v4 SHA-256**：`c3f570a94cc5de9f828324e8c16b15762be1330207a4ce9b6e010cfff119e15e`，24.0 MiB，arm64-v8a only，minSdk 26；字体位于 `reversible_mosaic/assets/fonts/wqy-microhei.ttc`；`buildozer.spec` 的 `source.include_exts` 已加 `ttf,ttc,txt`。
- **构建脚本增量化**：v4 起 `scripts/wsl_build_android.sh` 从 `rm -rf $WORKSPACE + rsync` 改为 `mkdir -p + rsync -a --delete --exclude ".buildozer/"`；下次改 py/spec 后重跑 3–5 min（而非 25–30 min 从零编 CPython/SDL2）。
- **【联合】用户已确认**：卸载重装 v4 后启动无闪退，首页 + 教程页 Latin + CJK 混排全部正常。

### 阶段 0 目前的达成情况
- ✅ arm64 APK 可安装、可启动、UI 可读、无网络权限
- ✅ Kivy 外壳 + SDL2 + libtvg + libwebp 已稳定打包并跑通
- ✅ 构建工具链稳定（p4a / gradle / libthorvg / GFW 障碍全部落对策；缓存复用）

### 阶段 0 v5 真机自检（2026-07-28，见 [docs/probe-report.md](docs/probe-report.md)）

**APK**：`bin/reversiblemosaic-0.1.0-arm64-v8a-debug-v5.apk`
（SHA-256 `5d6a0d9c6e5a9623b7e6518b25eb77d5a1f69041ce5f1a80e3e972eb9bb4c04c`，34.1 MiB）
**requirements**：`python3,kivy,pyjnius,numpy,pillow`（Stage 0 batch 1，Cython 走 v6）

**首页临时"阶段 0 自检"入口** → `reversible_mosaic/ui/self_test.py` `SelfTestScreen`（5 探针按钮 + 性能扫描 + 取消 + 结果落 App 私有目录）。

| 子项 | 结果 |
|---|---|
| 1. pyjnius 探针 | ✅ `autoclass OK; package=io.placeholder.reversiblemosaic` |
| 2. numpy 探针 | ✅ `numpy=2.3.0, arr.shape=(4, 4, 4), dtype=uint8` |
| 3. pillow 探针 | ✅ `PIL=11.3.0, 4x4 RGBA PNG=88B round-trip OK` |
| 4. 透明 RGB 零差异 on-device | ✅ 4x4 RGBA α=0，rounds 1/5/20 全部**逐字节相等** |
| 5. Cython v1_optimized | ⏳ NOT_BUILT（预期，v6 目标） |
| 6. 1920×1080 性能扫描 | ⚠️ 直接跑不动，用 256×256 参考实现替代；外推 20 轮 ≈ 20 min，比 AC-PERF 目标 35 s **慢 34×** |

**256×256 参考实现（真机）中位数**：1 轮 1.311 s / 10 轮 12.787 s / 20 轮 37.625 s；峰值 RSS 275 MiB。

**结论**：阶段 0 退出标准 5/6 完成。Cython v1_optimized 打包 + 接入 pipeline 遗留到 v6/阶段 1，是发布路径的关键前置（AC-PERF 需要 Cython 硬带 30× 加速才能过）。

### 阶段 0 v5 → v6 演进
1. **`setup.py`** 项目根就位（PC 侧 Cython 编译入口；MSVC 自动跳过），
   `p4a.setup_py = 1` 试过一轮：**p4a 不会自动跑 pip install**，模式下
   APK 里只剩 `main.pyc`，`reversible_mosaic/` 整个丢失 —— 回退到 loose file。
2. **v6 实际路径**：`scripts/wsl_build_v1_cython.sh` 在 buildozer 前把
   `v1.pyx` 交叉编译为 `v1.cpython-314-aarch64-linux-android.so`
   （Cython 3.x + NDK `aarch64-linux-android26-clang` + target Python 3.14 头），
   直接落在源码树；`buildozer.spec` `source.include_exts` 加 `so`；p4a 当
   loose file 打进 APK。
3. **`_probe_v1_cython` v6 装机 PASS**：`Cython 模块加载 OK;
   lift_forward/lift_inverse 复原一致`。
4. **numpy patch 已持久化**：`scripts/p4a_local_recipes/numpy/` 覆盖 p4a
   内置 recipe，加 `patches = ["patches/numpy_unordered_map_include.patch"]`；
   清 `.buildozer/` 后自动应用，无需人工。
5. **pipeline 集成不在 v6**：性能扫描仍跑 `reference_v1` 纯 Python 参考实现，
   Cython inner loops 只是"装进 APK 里"。真提速走阶段 1 的 wire-up。

### 阶段 0 v6 真机自检（2026-07-28，见 [docs/probe-report.md](docs/probe-report.md)）

**APK**：`bin/reversiblemosaic-0.1.0-arm64-v8a-debug-v6.apk`
（SHA-256 `928e478aeb0939bb8396c5d24e6cb89cc25c90dd94da713d217a3c34fbbdf7fd`，34.1 MiB）

| 子项 | 结果 |
|---|---|
| 5. **Cython v1_optimized** | ✅ **`Cython 模块加载 OK; lift_forward/lift_inverse 复原一致`** |
| 其他 4 项 | ✅ 无回归（pyjnius / numpy / pillow / V1 参考实现全部保持 PASS） |
| 6. 256×256 性能扫描（还是参考实现） | 20 轮 median 25.6 s，20 轮 p95 25.6 s（v5 是 37.6 s / 49.1 s，抖动而已） |

**阶段 0 达成 6/6，可以转向阶段 1。**

### 阶段 1 首要待办
1. **Cython 接入 pipeline**：把 `reference_v1.py` 里 `_lift_forward` / `_lift_inverse`
   / `_permute_forward` / `_permute_inverse` / `_diffuse_forward` / `_diffuse_inverse`
   六个内循环替换为 `reversible_mosaic.core.algorithm.v1` 的 Cython 版本；
   保留纯 Python 版本做规范 oracle（PC dev 环境或 Cython 不可用时兜底）。
   `registry.py` 里让 V1 encrypt/decrypt 优先跑 Cython 变体。
2. **重新真机基准 1920×1080**：Cython 接入后，AC-PERF 目标（1 轮 ≤ 3 s、
   10 轮 ≤ 18 s、20 轮 ≤ 35 s）应能达到；否则需再优化或考虑 C/Rust 迁移。
3. **视觉验收准备**：按 §12.3 组织 3 名检查者对固定 20 张图片做 1/5/10/20
   轮结果的"人脸/文字/主体是否可辨认"评价，并把像素变化率 / 相邻相关性 /
   边缘相似度阈值冻结进需求附录。
4. **V1 算法冻结**：`docs/algorithm-v1.md` 标 `frozen`；此后任何像素规则改动
   必须新增 V2，不能改 V1 字节输出（`tests/vectors/vectors.json` 是黄金锚点）。

### 阶段 1 – PC 侧完成情况（2026-07-28）

**已完成（自动）**：
1. **Cython 接入 pipeline**：新增 [optimized_v1.py](reversible_mosaic/core/algorithm/optimized_v1.py)，
   复用 `reference_v1` 的 `_derive_words / _round_key / _validate / _checkpoint` 编排逻辑，
   六个内循环全部替换为 `v1.pyx` 中的 `nogil` Cython 版本。
   [registry.py](reversible_mosaic/core/algorithm/registry.py) 加 `_resolve_v1_transforms()`：
   能 import `optimized_v1` 就用 Cython（arm64 Android/Linux/WSL），否则退回
   `reference_v1`（Windows PC + MSVC）。新增 `v1_implementation()` 探测函数，
   自检屏 / 测试可查当前后端是 `"cython"` 还是 `"reference"`。
2. **跨实现字节一致测试**：新增
   [tests/unit/test_optimized_v1.py](tests/unit/test_optimized_v1.py)，8 个尺寸/轮数/种子组合
   下 reference vs Cython 逐字节比对；Windows PC 上 21 个用例正确跳过。
   [tests/vectors/test_v1_vectors.py](tests/vectors/test_v1_vectors.py) 增加
   `test_registered_v1_matches_draft_fixed_vectors` — 断言当前 registry 里
   V1 的字节输出与 `algorithm_v1_draft.json` 完全一致。
3. **Property 测试加强**：
   [tests/property/test_algorithm_properties.py](tests/property/test_algorithm_properties.py)
   从单个 `test_v1_is_a_bijection`（80 例，1/5 轮）扩到 5 个性质：
   高轮数双射（10/20 轮，12 例）、确定性（40 例）、Alpha 通道值集合守恒（20 例）、
   非平凡输出（15 例）。
4. **视觉质量指标模块**：新增
   [reversible_mosaic/core/algorithm/quality.py](reversible_mosaic/core/algorithm/quality.py)，
   计算 §12.3.3 三项指标：像素变化率（RGB 通道级）、
   水平/垂直/对角相邻像素亮度相关性（Pearson）、
   Sobel 边缘图 Jaccard 相似度。9 个单元测试覆盖恒等/全变/纯色/RGBA/scrambled 场景。
5. **视觉验收样本生成器**：新增
   [scripts/generate_visual_review_set.py](scripts/generate_visual_review_set.py)，
   从 `artifacts/visual_review_sources/` 读源图，对每张跑 3 个种子
   （默认 500_000、辅助 314_159、987_654_321）× 4 个轮数（1/5/10/20），
   保存打码 PNG（含合法 tEXt 元数据）+ 汇总 `metrics.json` +
   打印用 `scorecard.md`（3 名检查者独立填写模板）。

**验证情况**：
- `pytest -q`：130 passed / 21 skipped（Cython 相关在 Windows 上正确跳过）
- `mypy` strict：28 文件全部通过
- `ruff check`：9 个错误全部是 baseline 里已存在的（scripts/ 侧 recipe/enumerate 遗留），
  本轮改动引入 **零** 新违规

**尚待用户参与**：
- **【联合】v7 真机基准（1920×1080）** ✅ **已完成 2026-07-28**：
  v7 APK（SHA-256 `628f74b0d08525803e839747864f8187e4589b036b6c8baf631325893d6f57f0`，
  34.14 MiB）在约 8 GB arm64 真机跑 1920×1080 RGB，5 次中位数：
  - 1 轮 0.060 s / 5 轮 0.268 s / 10 轮 0.543 s / 20 轮 1.072 s；峰值 RSS 274.7 MiB
  - **AC-PERF 每一项都以 ~33× 余量通过**（详见 [docs/probe-report.md](docs/probe-report.md#阶段-1-v7-真机基准-2026-07-28)）
  - 不需要迁移 C/Rust；Cython + `nogil` 内循环足够
- **【人工协助】固定视觉图集**：请提供 20 张内容丰富的 RGB 照片（人像、
  文字、场景、插画各若干） + 8 张 RGBA + 8 张边界图。每张记录 SHA-256 与
  来源/许可证。放到 `artifacts/visual_review_sources/`。之后我跑
  `python scripts/generate_visual_review_set.py`，出 `metrics.json` 报告
  再由你定阈值。
- **3 人视觉验收**：拿到 `scorecard.md` 后由你协调 3 名检查者独立填写。

### 阶段 1 后续待办
1. **v7 真机基准 + 阈值冻结**：拿到实测数字后把三项质量阈值和 AC-PERF
   实测中位数/P95 写进 `docs/algorithm-v1.md` 附录。
2. **UI 打通编码/解码屏**：`reversible_mosaic/app.py` 阶段 1 结束前需要
   把 `HomeScreen` 的两个 Placeholder 换成 `EncodeScreen` / `DecodeScreen`
   / `ProgressScreen` / `ResultScreen`（走 `TaskCoordinator` +
   `ProgressReporter`）。跨越阶段 1/2 边界；MVP 视觉可用之后再收
   `SelfTestScreen` 到"设置 → 诊断"。
3. **V1 冻结签字**：视觉阈值 + AC-PERF 数据齐备后，把
   `algorithm_v1_draft.json` 改名 `vectors.json`，`docs/algorithm-v1.md`
   翻 `frozen` 状态，附录列冻结日期和阈值表。
