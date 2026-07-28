# ReversibleMosaic 源码索引

**目的**：改代码前先看这一份文档就能知道该开哪个文件。每个条目给
"作用一句话、公开 API、上下游依赖、改动时该同步什么"。

按架构分层（应用层 → 领域层 → 核心层 → 算法 → 文件层 → 平台层 → UI →
资源 → 测试 → 构建/探测脚本 → 配置 → 文档）。

---

## 应用入口

### [`main.py`](../main.py)
- **作用**：Kivy `App.run()` 入口。仅 10 行，`if __name__ == "__main__"`
  时实例化 `ReversibleMosaicApp` 并 `run()`。
- **导入**：`reversible_mosaic.app.ReversibleMosaicApp`
- **谁调用它**：Buildozer / p4a 打包时按 `buildozer.spec` 的
  `source.include_patterns = main.py` 把它放进 APK 私有 tarball 顶层，
  Android bootstrap 会执行 `main.py`。PC 侧 `python main.py` 也能跑。
- **改动指引**：几乎不改。要换入口类名或加启动前的环境变量，改这里；否则
  改到 `app.py`。

### [`reversible_mosaic/__init__.py`](../reversible_mosaic/__init__.py)
- **作用**：包版本声明 `__version__ = "0.1.0"`；不做任何 import。
- **改动指引**：只有版本号需要动时改。发布 tag 前手动同步到 `pyproject.toml`
  的 `[project].version` 和 `buildozer.spec` 的 `version`。

### [`reversible_mosaic/app.py`](../reversible_mosaic/app.py)
- **作用**：Kivy 应用外壳。当前为阶段 0 探针版本：纯 Kivy（无 kivymd）；
  `LabelBase.register(name="Roboto", fn_regular="assets/fonts/wqy-microhei.ttc")`
  在 import 阶段把默认字体替换成覆盖 Latin+CJK 的 wqy-microhei；用
  `ScreenManager` 管理 `HomeScreen` / `TutorialScreen` / `PlaceholderScreen`
  三个占位屏。
- **关键 export**：`ReversibleMosaicApp(App)`、`HomeScreen(Screen)`、
  `TutorialScreen(Screen)`、`PlaceholderScreen(Screen)`。`_KV` 是内嵌的 KV
  语言字符串，`Builder.load_string(_KV)` 在 `build()` 里加载。
- **导入的外部包**：`kivy.app.App`、`kivy.core.text.LabelBase`、
  `kivy.lang.Builder`、`kivy.properties.StringProperty`、
  `kivy.uix.screenmanager.Screen`。
- **改动指引**：
  - 加新屏：在 `_KV` 里加 `<NewScreen>: name: "xxx"` block + 在
    `ScreenManager` 末尾添子节点 + Python 侧写 `NewScreen(Screen)` 类。
  - 改字体：改 `_CJK_FONT_PATH` 和 `LabelBase.register` 的 name 参数。
  - 阶段 1 会把这里替换成 `EncodeScreen` / `DecodeScreen` /
    `ProgressScreen` / `ResultScreen`，并挂接 `TaskCoordinator`（参见
    `core/task_coordinator.py`）。
  - **不要**在这里做像素处理 —— 屏只消费 view model，处理走 worker 线程。

---

## 领域层（`reversible_mosaic/domain/`）

无 Android 依赖的纯 Python 规则；PC 与 Android 共用。

### [`domain/share_code.py`](../reversible_mosaic/domain/share_code.py)
- **作用**：分享代码的解析、规范化、随机生成。空码映射到默认 `"500000"`；
  非空只接受 1–10 位 ASCII 十进制数字并按整数去前导零。
- **常量**：`DEFAULT_SHARE_CODE = "500000"`、`MIN_RANDOM_CODE = 100000`、
  `MAX_RANDOM_CODE = 999999`、`MAX_SEED = 9_999_999_999`。
- **导出**：`ShareCode(normalized, seed, used_default)` 数据类、
  `ShareCodeError(ValueError)`、`parse_share_code(value: str | None) -> ShareCode`、
  `generate_share_code() -> ShareCode`（用 `secrets.randbelow`，避开默认值）。
- **谁用它**：`core/pipeline.py` 调 `parse_share_code`；`ui/view_models.py` 里
  `TaskFormState.parsed_share_code()` 与 `randomize_share_code()`。
- **改动指引**：`DEFAULT_SHARE_CODE` 与 `MAX_SEED` 是**需求冻结项**，改动
  破坏跨版本可逆性；只能在 V2 里另定义，不能改 V1 语义。

### [`domain/task_state.py`](../reversible_mosaic/domain/task_state.py)
- **作用**：任务状态机的枚举 + 转换白名单。所有状态迁移必须走
  `transition(current, target)`，非法迁移抛 `InvalidTaskTransition`。
- **导出**：`TaskState(StrEnum)`（10 个状态：IDLE / IMAGE_SELECTED /
  NORMALIZING / NORMALIZED / PROCESSING / PREVIEW_READY / SAVING /
  COMMITTED / FAILED / CANCELLED）、`InvalidTaskTransition(RuntimeError)`、
  `transition(current, target) -> TaskState`。
- **谁用它**：`core/task_coordinator.py` 里 `TaskCoordinator._transition_locked`。
- **改动指引**：
  - 新增状态：加到 `TaskState` 枚举 + `_ALLOWED_TRANSITIONS` 里同时定义
    "从谁来、去谁"。
  - 修改迁移：一定要同步更新 `test_task_state.py` 的断言矩阵。

### [`domain/limits.py`](../reversible_mosaic/domain/limits.py)
- **作用**：P0 资源阈值（输入 50 MiB、边长 8192、总像素 12M、宽高比 64:1、
  JPEG segment 1 MiB、PNG 文本累计 64 KiB、内存 60% 上限）。给出无需分配的
  预算估算。
- **常量**：`MAX_INPUT_BYTES`、`MAX_EDGE`、`MAX_PIXELS`、`MAX_ASPECT_RATIO`、
  `MAX_SEGMENT_BYTES`、`MAX_PNG_TEXT_BYTES`、`MAX_FULL_SIZE_BUFFERS = 3`、
  `MEMORY_FRACTION_LIMIT = 0.60`。
- **导出**：`ResourceLimitError(ValueError)`、
  `ResourceEstimate(pixel_bytes, full_size_buffers, fixed_overhead)`
  数据类（含 `peak_bytes` 属性）、`validate_dimensions(w, h)`、
  `estimate_peak_memory(w, h, channels, *, full_size_buffers, fixed_overhead)`、
  `validate_available_memory(estimate, available_bytes)`。
- **谁用它**：`io/probe.py` 与 `io/normalize.py`（预扫描时调 `validate_dimensions`）。
  未来在 Android 侧读取 `ActivityManager.MemoryInfo` 后调 `validate_available_memory`。
- **改动指引**：这些是**需求档 AC-011/AC-014 的支撑**。放宽任何阈值都会牵扯
  性能与稳定性验证，需先在 `docs/algorithm-v1.md` 备注理由。

### [`domain/tasks.py`](../reversible_mosaic/domain/tasks.py)
- **作用**：线程安全的取消 token 和进度回调聚合器。这是"协作式取消"的核心。
- **导出**：
  - `ProgressCallback = Callable[[str, float | None], None]`
  - `CancellationToken`：内部包 `threading.Event`，提供 `cancel()` /
    `is_cancelled()` / `probe()` / `reset()`。`probe` 与 `is_cancelled` 语义
    相同，但 `probe` 是给算法内部 `_checkpoint(cancel)` 用的谓词签名。
  - `ProgressReporter`：`bind(callback)` 绑一次；`report(stage, fraction)`
    转发。回调若为 None 则丢弃 —— 便于测试。
- **谁用它**：`core/task_coordinator.py`（拥有一个 token 一个 reporter）、
  `core/pipeline.py`（接受 `cancel: CancellationProbe` 与
  `progress: ProgressReporter`）、算法内部 `_checkpoint(cancel)`。
- **改动指引**：**不要**在算法长循环里"每像素"调 probe，粒度太细；
  reference_v1 是"每轮 3 次"（lift 前、permute 前、diffuse 前），
  Cython v1.pyx 释放 GIL 期间不查取消，需要主循环外套 checkpoint。

### [`domain/__init__.py`](../reversible_mosaic/domain/__init__.py)
- 仅 docstring，无 import。

---

## 核心层（`reversible_mosaic/core/`）

调度、编排 与 高层管线。

### [`core/pipeline.py`](../reversible_mosaic/core/pipeline.py)
- **作用**：一张图 encrypt/decrypt 的端到端管线：`normalize → transform →
  write_png`。签发三个 stage 常量给 UI/协调器做进度显示。
- **常量**：`STAGE_NORMALIZE = "normalize"`、`STAGE_TRANSFORM = "transform"`、
  `STAGE_WRITE = "write"`。
- **导出**：
  - `PipelineResult(output_path, pixels, source, algorithm_version, rounds,
    share_code)` 冻结数据类。
  - `process_image(input_path, output_path, *, operation, rounds, share_code,
    algorithm_version=None, cancel=None, progress=None) -> PipelineResult`。
    `operation` 必须是 `"encrypted"` 或 `"restored"`；解密时用
    `algorithm_version` 拿指定版本，加密始终用 `latest()`。
- **导入链**：`algorithm.contracts.PixelArray`、`algorithm.registry.get/latest`、
  `domain.share_code.parse_share_code`、`domain.tasks.ProgressReporter`、
  `io.normalize.normalize_image / write_png`、`io.png_metadata.MosaicMetadata`。
- **谁用它**：`core/task_coordinator.TaskCoordinator._run`（worker 线程里调）、
  测试 `tests/unit/test_pipeline.py`。
- **改动指引**：
  - 加新 stage → 在这里定义常量、在合适位置调 `progress.report(stage, 0.0)`，
    并去 `core/task_coordinator.py::_sync_state_to_stage_locked` 加对应的
    状态迁移。
  - **绝不**在这里加"保存到系统相册"逻辑；那走 Android gateway。

### [`core/task_coordinator.py`](../reversible_mosaic/core/task_coordinator.py)
- **作用**：worker 线程封装 + 状态机 + 进度桥。UI 线程调 `start(request)`，
  worker 线程跑 `process_image`，成功/失败/取消/进度回调都通过
  `schedule_on_main` 回到 UI 线程再调外部回调 —— 让所有 Kivy widget 操作
  只在主线程发生。
- **类型别名**：`Operation = Literal["encrypted", "restored"]`、
  `MainThreadScheduler = Callable[[Callable[[], None]], None]`。
- **导出**：
  - `TaskRequest(operation, input_path, output_path, rounds, share_code,
    algorithm_version=None)` 冻结数据类。
  - `TaskCoordinatorError(RuntimeError)`（契约违反，非业务错误）。
  - `TaskCoordinator(schedule_on_main=None)`：
    - 属性 `state` (返回 `TaskState`)、`on_state_change` / `on_progress` /
      `on_completed` / `on_failed` / `on_cancelled` 五个可写回调。
    - 方法 `start(request)`、`cancel()`、`join(timeout=None)`、`reset()`。
- **默认 scheduler**：`_run_now`（同步执行）—— 测试用；Kivy 侧要传
  `Clock.schedule_once` 的 lambda。
- **谁用它**：阶段 1 的 `EncodeScreen` / `DecodeScreen` 会 own 一个协调器；
  测试 `tests/unit/test_task_coordinator.py` 覆盖成功/失败/取消/双启动/reset。
- **改动指引**：
  - 想让 UI 显示 "写入 PNG" 阶段？`_sync_state_to_stage_locked` 里
    `STAGE_WRITE` 分支已经故意留白（状态不动、只让进度回调透传），
    不要在这里 introduce SAVING 状态 —— SAVING 是 Android 侧
    MediaStore pending 事务的状态，是阶段 2 的事。
  - `_run` 里 `except BaseException`（不是 Exception）是为了捕获
    `SystemExit`/`KeyboardInterrupt` —— worker 线程被杀时也要走
    `_deliver_cancelled`/`_deliver_failed`。

### [`core/__init__.py`](../reversible_mosaic/core/__init__.py)
- 仅 docstring。

---

## 算法（`reversible_mosaic/core/algorithm/`）

V1 参考实现 + Cython 优化候选。**冻结前**任何逐字节改动都是有效的；冻结后
（`docs/algorithm-v1.md` 标 "frozen"）只能新增 V2，不能修改 V1。

### [`algorithm/contracts.py`](../reversible_mosaic/core/algorithm/contracts.py)
- **作用**：算法边界契约 —— 类型、模式、轮数集合、异常类、像素校验。
- **导出**：
  - 类型：`PixelMode = Literal["RGB", "RGBA"]`、
    `PixelArray = npt.NDArray[np.uint8]`。
  - 常量：`VALID_ROUNDS = frozenset({1, 5, 10, 20})`。
  - 异常：`AlgorithmError(ValueError)`、`CancellationRequested(RuntimeError)`。
  - Protocol：`CancellationProbe`（`__call__() -> bool`）。
  - 数据类：`ImageSpec(width, height, mode)`（含 `channels` 属性）。
  - 函数：`validate_pixels(pixels, spec)` —— 检查 dtype/shape/C-contiguous。
- **谁用它**：`reference_v1.py`、`registry.py`、`pipeline.py`、`normalize.py`。
- **改动指引**：`VALID_ROUNDS` 是需求冻结项。类型 alias 供 IDE 与 mypy，
  不影响运行时。

### [`algorithm/registry.py`](../reversible_mosaic/core/algorithm/registry.py)
- **作用**：版本 registry。模块加载时 `_register_builtin_versions()` 会自动
  注册 V1，指向 `reference_v1.encrypt / decrypt`。
- **类型别名**：`Transform = Callable[[PixelArray, int, int, CancellationProbe | None], PixelArray]`。
- **导出**：
  - `AlgorithmDescriptor(version, display_name, release_date, encrypt, decrypt)`
    冻结数据类。
  - `register(descriptor)`、`get(version) -> AlgorithmDescriptor`、
    `supported_versions() -> tuple[...]`（版本号���序）、
    `latest() -> AlgorithmDescriptor`。
- **谁用它**：`core/pipeline.py::process_image` —— 加密调 `latest()`，解密调
  `get(algorithm_version or latest().version)`。
- **改动指引**：
  - **加 V2**：新建 `reference_v2.py`，在 `_register_builtin_versions()` 追加
    `register(AlgorithmDescriptor(version=2, ..., encrypt=..., decrypt=...))`。
    `latest()` 会自动返回 V2。
  - **切换到 Cython 优化实现**：让 `_register_builtin_versions` 尝试
    `import reversible_mosaic.core.algorithm.v1_optimized`；成功则用
    优化版的 encrypt/decrypt，失败回退到 `reference_v1`。当前尚未做这个
    fallback wire-up，阶段 1 才做。

### [`algorithm/reference_v1.py`](../reversible_mosaic/core/algorithm/reference_v1.py)
- **作用**：V1 参考实现，"规范代表"。纯 Python 逐像素运算，慢但可读，
  是固定向量 (fixed vectors) 的 ground truth。
- **常量**：`_DOMAIN = b"reversible_mosaic/algorithm/v1\x00"`（域分离标签）、
  `_MASK64`。
- **内部函数**（下划线开头，不外部导出）：
  - `_splitmix64(value)` —— PRF，来自 splitmix64 家族。
  - `_derive_words(spec, seed) -> (lift_key, permute_key, diffuse_fwd_key,
    diffuse_rev_key)` —— SHA-256 派生 4 个 64-bit word。
  - `_round_key(word, round_index, domain)` —— 每轮 4 个子密钥。
  - `_mask3(key, index) -> (m0, m1, m2)` —— 每像素 3 通道掩码。
  - `_checkpoint(cancel)` —— 取消 probe，抛 `CancellationRequested`。
  - `_lift_forward / _lift_inverse` —— RGB 三角 lifting（`r += 3g + 5b + m0`；
    Alpha 完全不参与）。
  - `_permute_forward / _permute_inverse` —— Fisher–Yates，正向 `N-1→1`，
    逆向 `1→N-1` 用相同 PRF 重生成索引。
  - `_diffuse_forward / _diffuse_inverse` —— 反馈链扩散，`reverse=True`
    走反向扫描；Alpha 只随空间移动、数值不改。
  - `_validate(pixels, rounds) -> ImageSpec` —— 轮数/模式/形状校验。
- **导出**：
  - `encrypt(pixels, seed, rounds, cancel=None) -> PixelArray`
  - `decrypt(pixels, seed, rounds, cancel=None) -> PixelArray`
- **每轮顺序**：encrypt 是 `lift → permute → diffuse_fwd → diffuse_rev`；
  decrypt 反转顺序 `diffuse_rev⁻¹ → diffuse_fwd⁻¹ → permute⁻¹ → lift⁻¹`，
  轮次从 `rounds-1` 递减到 0。
- **谁用它**：`registry.py::_register_builtin_versions`、
  `tests/unit/test_algorithm_v1.py`、`tests/property/test_algorithm_properties.py`、
  `tests/vectors/generate_v1_vectors.py`、`tests/vectors/test_v1_vectors.py`。
- **改动指引**：**冻结前**只允许改字节输出如果同时更新固定向量文件。
  冻结后（有 `docs/algorithm-v1.md` 标记）一个字节都不能动，改动 = 破坏
  跨版本可逆性。

### [`algorithm/v1.pyx`](../reversible_mosaic/core/algorithm/v1.pyx)
- **作用**：Cython 优化候选，把 `reference_v1.py` 的四个内循环
  （`lift_forward/inverse`、`permute_forward/inverse`、
  `diffuse_forward/inverse`）用 memoryview + `nogil` 重写。跟 Python 版
  **每个字节一致**（同样的 splitmix64 常量、同样的通道更新顺序、同样的
  `rm_mul_hi_64` 用于无偏乘法映射）。
- **导出**（`cpdef`）：`lift_forward(pixels, key)`、`lift_inverse(pixels, key)`、
  `permute_forward(pixels, key)`、`permute_inverse(pixels, key)`、
  `diffuse_forward(pixels, key, reverse)`、`diffuse_inverse(pixels, key, reverse)`。
- **状态**：Windows PC 已能编译进 `.pyd`；Android arm64 打包还没接上（需要
  在 `buildozer.spec` 加 Cython 相关 recipe 且提供 `setup.py`）。
- **谁用它**：**目前无生产调用**。将来 `registry.py` 会尝试 import 这个模块，
  成功则替换 encrypt/decrypt 的实现。
- **改动指引**：
  - `.pyx` 修改后必须 `python setup.py build_ext --inplace` 重新编译。
  - Cython 内 `with nogil:` 段不能碰 Python 对象，也不能调 `_checkpoint`
    —— 取消检查只能在 Python 侧的主循环里做（每轮之间）。
  - **必须保证与 `reference_v1.py` 逐字节一致**，否则 registry fallback 时
    行为不确定；改一处两处都要同步改。

### [`algorithm/__init__.py`](../reversible_mosaic/core/algorithm/__init__.py)
- 仅 docstring。

---

## 文件层（`reversible_mosaic/io/`）

安全解码 + 严格协议序列化 + 复读校验。

### [`io/probe.py`](../reversible_mosaic/io/probe.py)
- **作用**：**在 Pillow 之前**手动扫描 PNG chunk，做 header/大小/CRC/文本累计
  的边界检查，拒绝解压炸弹、动画 PNG、非 8-bit RGB/RGBA、参数异常等。
- **常量**：`PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"`、`MAX_CHUNK_BYTES = 50 MiB`。
- **导出**：
  - `ImageProbeError(ValueError)` —— 拒绝理由的公共基类。
  - `PngProbe(width, height, mode, chunks)` —— chunks 是保留的 `tEXt/zTXt/iTXt`
    元数据，供 `png_metadata.parse_png_metadata` 后续解析。
  - `scan_png(path) -> PngProbe`。
- **谁用它**：`io/normalize.py::normalize_image`（PNG 分支）、`write_png` 的
  写后校验。
- **改动指引**：这里的每一条 `raise` 都对应需求档一个"拒绝理由"，去掉一个
  就打开一个攻击面。要新增 chunk 类型的支持，加白名单不要加黑名单。

### [`io/normalize.py`](../reversible_mosaic/io/normalize.py)
- **作用**：PNG/JPEG 的统一入口。签名判定 → 有界 preflight → Pillow 解码 →
  EXIF Orientation transpose → 拒绝非 P0 模式 → 返回连续的 uint8 numpy 矩阵。
  同时提供 `write_png` 做**写后复读**校验（scan_png + np.array_equal）。
- **导出**：
  - `NormalizedImage(pixels, input_format, input_bytes)` 冻结数据类
    （含 `mode` / `width` / `height` 属性）。
  - `normalize_image(path) -> NormalizedImage`。
  - `write_png(path, pixels, metadata) -> None` —— 写入失败时会 `unlink` 目标。
- **内部**：`_preflight_jpeg(source)` 扫描 JPEG segment 大小，防止无界 EXIF。
- **谁用它**：`core/pipeline.process_image`（两处：读入 & 写出）；
  `tests/unit/test_normalize.py`、`test_exif_orientation.py`。
- **改动指引**：
  - **不要**移除写后 `np.array_equal` 校验 —— 这是需求 AC-006/014 的最后
    防线（编码器 bug 或磁盘 corruption 立即暴露）。
  - JPEG 只支持普通 8-bit RGB；灰度、CMYK、YCbCr subsample 特殊模式都得
    显式拒绝。

### [`io/png_metadata.py`](../reversible_mosaic/io/png_metadata.py)
- **作用**：`reversible_mosaic` PNG tEXt 元数据的严格 schema —— 定长键、
  长度上界、只接受 `tEXt`（不接受 `zTXt/iTXt` —— 防压缩炸弹），
  ASCII-only JSON、精确类型（拒绝 `int` 的地方绝对不能收 `bool` 或 `float`）。
- **常量**：`METADATA_KEYWORD = b"reversible_mosaic"`、`MAX_VALUE_BYTES = 2048`、
  `MAX_CANDIDATES = 4`、`MAX_TOTAL_TEXT_BYTES = 64 KiB`。
- **导出**：
  - `MetadataStatus(StrEnum)`：VALID / ABSENT / INVALID / CONFLICT。
  - `MosaicMetadata(schema_version, app_marker, operation_type,
    algorithm_version, rounds, pixel_mode, width, height)` —— 冻结数据类。
  - `MetadataResult(status, metadata, reason)` —— 解析结果三元组。
  - `serialize_metadata(metadata) -> str`（deterministic JSON, ASCII-only）。
  - `parse_png_metadata(chunks, *, actual_mode=None, actual_size=None) -> MetadataResult`。
- **谁用它**：`core/pipeline.process_image`（构造 MosaicMetadata）、
  `io/normalize.write_png`（序列化后写入 tEXt）；未来解密路径要用
  `parse_png_metadata` 从输入 PNG 里拿到 `algorithm_version` / `rounds`。
- **改动指引**：schema 是**协议冻结项**。可以新增字段（在 `_validate` 里
  设默认值即可保持向后兼容），但**不能改字段名或类型**。

### [`io/__init__.py`](../reversible_mosaic/io/__init__.py)
- 仅 docstring。

---

## 平台层（`reversible_mosaic/android/`）

抽象接口 + PC 侧假实现。真正的 PyJNIus 实现（Photo Picker、SAF、MediaStore、
Intent、剪贴板）在阶段 2 才写。

### [`android/gateways.py`](../reversible_mosaic/android/gateways.py)
- **作用**：三个 `Protocol`（结构类型）定义业务与平台的边界。
- **导出**：
  - `InputGateway`：`import_to_cache(uri, cache_dir) -> Path` —— 把选中 URI
    的字节安全复制到 app 私有缓存。
  - `OutputGateway`：`publish_png(source, display_name) -> str` /
    `open_for_view(handle)` / `share(handle, subject)`。
  - `ClipboardGateway`：`copy_sensitive(text)` —— 分享码复制且尽量标"敏感"。
- **谁用它**：阶段 1/2 的屏幕代码；测试用 fake 实现（PC 走 desktop.py）。
- **改动指引**：改这些方法签名会同时影响 Android 与 desktop 两个实现，
  只在需要暴露新平台能力（如 URI 授权 API）时改。

### [`android/desktop.py`](../reversible_mosaic/android/desktop.py)
- **作用**：PC 侧假实现。用 `shutil.copyfile` 做 import；
  `publish_png` 写到指定目录（重名自动 `_1/_2` 后缀）；`open_for_view` /
  `share` / `copy_sensitive` 都是 no-op（PC 不需要）。
- **导出**：`DesktopInputGateway`、`DesktopOutputGateway(output_dir)`、
  `DesktopClipboardGateway`。
- **改动指引**：PC 端跑冒烟测试或性能扫描时用。**不要**在这里加平台特定
  API（比如 Windows 剪贴板/dialog），那样会让"PC 假实现"退化成
  另一个平台层。

### [`android/__init__.py`](../reversible_mosaic/android/__init__.py)
- 仅 docstring `"""Android platform adapters."""`。

---

## UI（`reversible_mosaic/ui/`）

### [`ui/view_models.py`](../reversible_mosaic/ui/view_models.py)
- **作用**：不依赖 Kivy 的表单/进度/结果 view model。屏在主线程持有实例，
  worker 通过 `TaskCoordinator` 回调更新。这样 view model 可以被
  pytest 直接测。
- **常量**：`VALID_ROUNDS = (1, 5, 10, 20)`、`DEFAULT_ROUNDS = 5`。
- **导出**：
  - `TaskFormState(operation, input_path=None, share_code="", rounds=5)`：
    - `parsed_share_code() -> str | None` （抛 `ShareCodeError`）。
    - `randomize_share_code() -> None`。
    - `can_start() -> bool`（输入路径 + 合法 rounds + 合法 share_code）。
  - `ProgressSnapshot(stage, fraction, label)`：`from_stage(stage, fraction)`
    工厂方法把 pipeline stage 常量映射为中文标签（normalize→"规范化"，
    transform→"算法处理"，write→"写入 PNG"）。
  - `ResultSnapshot(output_path, algorithm_version, rounds, share_code_display)`：
    `from_pipeline(result)` 工厂。
- **谁用它**：阶段 1 的编码/解码/进度/结果屏；测试 `tests/unit/test_view_models.py`。
- **改动指引**：不要在这里 import kivy 或 kivymd（会破坏 pytest 便捷跑测）。
  UI 只应该"读"这些 dataclass 的字段，不要把 Kivy widget 引用塞进来。

### [`ui/__init__.py`](../reversible_mosaic/ui/__init__.py)
- 仅 docstring `"""UI-layer helpers (view models + Kivy screens)."""`。

### [`ui/self_test.py`](../reversible_mosaic/ui/self_test.py)
- **作用**：**阶段 0 临时诊断屏**。5 个探针按钮（pyjnius / numpy / pillow /
  V1 参考实现透明 RGBA / V1 Cython 优化）+ 性能扫描按钮 + 取消按钮 +
  可滚动结果 TextInput。用于在真机上验证每个 arm64 原生依赖打包 +
  加载 + 运行是否正常。阶段 0 退出后从首页删入口（`app.py` 里 
  `"阶段 0 自检 (临时)"` Button），本模块保留以做回归。
- **导出**：
  - `SelfTestScreen(Screen)`：程序化构建 widget 树（不用 KV），
    在 `__init__` 里挂 5 个探针按钮 + 性能扫描 + 取消 + 清空结果 + 返回首页。
    perf 扫描跑 `threading.Thread`，通过 `Clock.schedule_once` 回主线程更新
    Label；取消用 `threading.Event`。
  - `SYNC_PROBES`：`(label, callback)` 列表，同步探针；每项独立可点。
  - 模块级探针函数（下划线开头，测试可直接调用）：
    `_probe_pyjnius / _probe_numpy / _probe_pillow /
    _probe_reference_v1 / _probe_v1_cython`。
  - 辅助：`_peak_rss_bytes()`（stdlib `resource` 优先, fallback
    `/proc/self/status`）、`_fmt_bytes()`。
- **数据落盘**：性能扫描完成时写 `{App.user_data_dir}/stage0_perf.json`
  （字段：implementation、resolution、rows[rounds/iterations/median_s/p95_s/
  peak_rss_bytes]、cancelled、timestamp、python、machine）。
- **谁用它**：`app.py` import + 首页 "阶段 0 自检 (临时)" 按钮跳转；
  `tests/unit/test_self_test_probes.py` 覆盖 PC 端可跑的 4 个探针。
- **改动指引**：
  - **临时模块**，不要在这里放生产逻辑；生产屏（EncodeScreen 等）走 view_models。
  - 加新探针：在 `SYNC_PROBES` 追加 `("标签", _probe_xxx)`；探针必须
    返回字符串或抛异常 —— UI 侧统一 catch。
  - 性能扫描目前跑 256x256 reference —— 阶段 1 把 Cython 接到 pipeline
    后可换成 1920x1080 optimized。
  - 阶段 0 退出后：只删 `app.py` 里的 HomeScreen 按钮和 KV `SelfTestScreen:`
    条目；保留本文件供回归。

---

## 资源（`reversible_mosaic/assets/`）

### [`assets/fonts/wqy-microhei.ttc`](../reversible_mosaic/assets/fonts/wqy-microhei.ttc)
- 5.2 MiB TTC。WenQuanYi Micro Hei（文泉驿微米黑）face 0 = Sans（Latin + SC）。
  被 `app.py` 里 `LabelBase.register(name="Roboto", fn_regular=...)` 全局
  替换默认字体。
- 授权：Apache-2.0 或 GPL-3+ with Font exception（见同目录 LICENSE.txt）。
- **改动指引**：换字体要同步改 `app.py` 的 `_CJK_FONT_PATH` 与
  `buildozer.spec` 的 `source.include_exts`（保留 `ttf,ttc,txt`）。

### [`assets/fonts/LICENSE.txt`](../reversible_mosaic/assets/fonts/LICENSE.txt)
- wqy-microhei 的许可声明。发布 APK 时会一起打入 tarball。

---

## 测试（`tests/`）

按分层组织，`pytest -q` 默认全跑。

### `tests/unit/`
每个测试文件对应一个模块，同名前缀 `test_`。命中率高，跑得快。

| 文件 | 覆盖模块 | 主要断言 |
|------|---------|---------|
| [`test_share_code.py`](../tests/unit/test_share_code.py) | `domain/share_code.py` | 空/超长/非数字/超大 seed；随机码避开默认值 |
| [`test_task_state.py`](../tests/unit/test_task_state.py) | `domain/task_state.py` | 每对合法迁移 + 反向非法迁移 |
| [`test_limits.py`](../tests/unit/test_limits.py) | `domain/limits.py` | 边长/像素/宽高比/内存分数上限 |
| [`test_probe.py`](../tests/unit/test_probe.py) | `io/probe.py` | 有效 PNG、CRC 失败、chunk 截断、text 累计 |
| [`test_normalize.py`](../tests/unit/test_normalize.py) | `io/normalize.py` | PNG/JPEG 分支、非法模式、write 写后校验 |
| [`test_png_metadata.py`](../tests/unit/test_png_metadata.py) | `io/png_metadata.py` | schema 校验、tEXt only、重复 keyword |
| [`test_exif_orientation.py`](../tests/unit/test_exif_orientation.py) | `io/normalize.py` JPEG EXIF | Orientation 1–8 都正确 transpose |
| [`test_algorithm_v1.py`](../tests/unit/test_algorithm_v1.py) | `algorithm/reference_v1.py` | 边缘尺寸、Alpha 保真、非法输入 |
| [`test_pipeline.py`](../tests/unit/test_pipeline.py) | `core/pipeline.py` | encrypt→decrypt 闭环、stage 顺序、cancel 传递 |
| [`test_task_coordinator.py`](../tests/unit/test_task_coordinator.py) | `core/task_coordinator.py` | 成功/失败/取消/双启动/reset |
| [`test_view_models.py`](../tests/unit/test_view_models.py) | `ui/view_models.py` | 表单 can_start、progress 标签映射 |
| [`test_self_test_probes.py`](../tests/unit/test_self_test_probes.py) | `ui/self_test.py` | PC 端可跑的 4 个探针（numpy/pillow/reference_v1/v1_cython），pyjnius 探针在 PC 上应 ImportError |

### [`tests/property/test_algorithm_properties.py`](../tests/property/test_algorithm_properties.py)
- 用 Hypothesis 生成任意 `(w, h, mode, seed, rounds)`，断言
  `decrypt(encrypt(x)) == x`、确定性、前导零等价。是 V1 冻结前"打不同种子
  跑不出 bug"的主要防线。

### [`tests/vectors/`](../tests/vectors/)
- [`generate_v1_vectors.py`](../tests/vectors/generate_v1_vectors.py)：合成
  固定图集，跑 1/5/10/20 轮，把 encrypt 输出与关键中间阶段摘要写入
  `vectors.json`（供跨平台比对）。
- [`test_v1_vectors.py`](../tests/vectors/test_v1_vectors.py)：读取
  `vectors.json`，断言当前 `reference_v1` 输出与文件一致。这是"防
  意外修改 V1 字节输出"的兜底。
- **改动指引**：改 `reference_v1.py` 后必须重跑 `generate_v1_vectors.py`
  更新固定向量；否则 `test_v1_vectors.py` 会红。冻结后重跑 = 破坏冻结。

### [`tests/adversarial/test_malicious_inputs.py`](../tests/adversarial/test_malicious_inputs.py)
- 恶意 PNG/JPEG 拒绝测试：伪造尺寸、异常 EXIF、chunk 截断、超大文本、
  非白名单 color_type、动画 PNG 等，全部应抛 `ImageProbeError`。

---

## 构建 & 探测脚本（`scripts/`）

### 主构建

#### [`scripts/wsl_build_android.sh`](../scripts/wsl_build_android.sh)
Buildozer 打包主入口，**只在 WSL Ubuntu 里跑**（`wsl -d Ubuntu -- bash
scripts/wsl_build_android.sh`）。做的事：
1. 杀掉遗留的 `buildozer` / `python-for-android` 进程（不含自身 PID）。
2. **增量** `rsync -a --delete --exclude ".buildozer/"` 从 Windows 侧
   同步源码到 `/home/hydrogen/src/ReversibleMosaic/`。**关键**：保留
   `.buildozer/build/` 目录（CPython/SDL2/kivy 的编译产物），下次改 py
   只花 3–5 min，而不是 25–30 min 全量重编。
3. 从 `~/.p4a-source-cache/` hard-link tarball 到 workspace 里
   `packages/`，让 p4a 全程跳过网络。
4. 通过 `GIT_CONFIG_COUNT/KEY_0/VALUE_0` 把 recipe 里
   `https://github.com/*` clone 重定向到 `https://ghfast.top/https://github.com/*`
   镜像 —— **每次调用生效，不改用户 `~/.gitconfig`**。
5. `cd $WORKSPACE && exec buildozer android debug`，同步写日志到
   `/home/hydrogen/src/reversible-mosaic-build.log`。

**改动指引**：
- **绝对不要**恢复 `rm -rf $WORKSPACE` —— 每轮都会从零重编 CPython。
- 不要动用户全局 git config；用现有的 `GIT_CONFIG_*` 环境变量方式。
- 加新的镜像可以直接改脚本里 `GIT_CONFIG_VALUE_0`。

#### [`scripts/wsl_prefetch_p4a.sh`](../scripts/wsl_prefetch_p4a.sh)
一次性预取 p4a 需要的全部 tarball（hostpython3, jpeg, libffi, libwebp,
openssl, png, sdl2/sdl2_image/sdl2_mixer/sdl2_ttf, sqlite3, python3, kivy,
pyjnius, libthorvg, setuptools 等）到 `~/.p4a-source-cache/<recipe>/`，
带 `.mark-<basename>` sentinel 让 p4a 的 `download_if_necessary()` 跳网。
GitHub URL 走 `ghfast.top`；OpenSSL 直接走 GitHub 发布 tarball（官方站
301 到 github）。

**改动指引**：只在 recipe 版本升级或加新 recipe 时重跑。之后
`wsl_build_android.sh` 会自动 hard-link。

### 网络探测（历史遗留，只在诊断新阻断时用）

#### [`scripts/probe_mirrors.sh`](../scripts/probe_mirrors.sh)
HEAD 探测 5 个 GitHub 加速代理（`mirror.ghproxy.com`、`ghfast.top`、
`ghproxy.link`、`gh-proxy.com`、`github.moeyy.xyz`）的 HTTP code。
当前使用的是 `ghfast.top`。

#### [`scripts/probe_git_mirrors.sh`](../scripts/probe_git_mirrors.sh)
对每个候选镜像跑一次 `git clone --depth 1 -b v9e-SDL libsdl-org/jpeg` 30 s
超时，验证 git+HTTPS smart protocol 能穿过。比 HEAD 更严格。

#### [`scripts/probe_direct_sources.sh`](../scripts/probe_direct_sources.sh)
探测非 GitHub 的直连 URL（`storage.googleapis.com` 上的 libwebp、
`openssl.org` 官方 tarball），确认是否需要额外镜像。

### 调试专用

#### [`scripts/inspect_sdl2_image_submodules.sh`](../scripts/inspect_sdl2_image_submodules.sh)
读 `sdl2_image` build tree 下所有 `.gitmodules` 文件。诊断 SDL2_image
子模块 clone 报错时用。历史上帮助定位过 `libjxl → skcms → skia.googlesource.com`
链路完全不可达 → 已在 p4a `sdl2_image/__init__.py` 就地跳过 libjxl/libavif。

#### [`scripts/enumerate_recipes.py`](../scripts/enumerate_recipes.py)
遍历 `RECIPES` 列表，打印每个 p4a `Recipe.versioned_url` 与本地 basename。
**必须在能 import `pythonforandroid` 的环境里跑**（WSL 的 build-venv）。用于
让预取脚本对齐 URL / 文件名。

#### [`scripts/wsl_patch_numpy_include.sh`](../scripts/wsl_patch_numpy_include.sh)
一次性补丁：给已解压的 numpy 2.3.0 `unique.cpp` 追加 `#include <unordered_map>`。
NDK r25b clang-14 + libc++ 没有 GCC/glibc 的传递包含，numpy 2.3.0 源码只 include
了 `<unordered_set>`，编译 `libunique_hash.a` 时报 "no template named
'unordered_map'"。幂等（已打过就跳）；每次清 `.buildozer/` 后必须再跑一次。
理想做法是把补丁抬到 p4a 的 numpy `apply_patches`；本轮 Stage 0 v5 走脚本手工。
- 触发条件：`unique.cpp` 出现在
  `.buildozer/android/platform/build-arm64-v8a/build/other_builds/numpy/arm64-v8a__ndk_target_26/numpy/numpy/_core/src/multiarray/`
  之后、meson 编译 `libunique_hash.a` 之前。
- **v6 已被本地 p4a recipe 覆盖代替**（见下条 `scripts/p4a_local_recipes/numpy/`）；
  这个脚本仅作为紧急手动兜底。

#### [`scripts/wsl_build_v1_cython.sh`](../scripts/wsl_build_v1_cython.sh)
v6 引入。**在 buildozer 之前**把 `reversible_mosaic/core/algorithm/v1.pyx` 交叉编译为
`reversible_mosaic/core/algorithm/v1.cpython-314-aarch64-linux-android.so`，
直接落在 WSL workspace 的源码树里，让 buildozer 当 loose file 打进 APK。
- **步骤**：
  1. `cython -3` 把 `.pyx` → `.c`
  2. NDK `aarch64-linux-android26-clang -shared -fPIC` 把 `.c` → `.so`
     链接 target Python 3.14 `libpython3.14.so` + `liblog`
  3. 目标 Python 3.14 头文件在
     `.buildozer/android/platform/build-arm64-v8a/build/other_builds/python3/arm64-v8a__ndk_target_26/python3/android-build/android-root/include/python3.14/`
- **首次冷启动**（`.buildozer/` 不存在或 dist 未建）时目标 Python 头缺席，
  脚本只做 cython → .c 一步，返回 0；`wsl_build_android.sh` 检测到后继续跑
  buildozer，dist 建好后**要求二次调用本脚本**才能得到 .so。
- **谁调用**：`wsl_build_android.sh` 在 rsync + prefetch 之后、buildozer 之前
  调一次；不进 APK（`scripts/` 在 `source.exclude_dirs`）。
- **改动指引**：加新 .pyx → 更新脚本里的 `SRC`/`GEN_C`/`OUT_SO` 或改成循环处理
  多个模块；确保输出 `.so` 名字含 `cpython-<py-major><py-minor>-<abi>-linux-android`
  这样 CPython 才认。

### p4a 本地 recipe 覆盖

#### [`scripts/p4a_local_recipes/numpy/__init__.py`](../scripts/p4a_local_recipes/numpy/__init__.py)
- **作用**：v6 引入。本地覆盖 p4a 内置 numpy 2.3.0 recipe，多的一行
  `patches = ["patches/numpy_unordered_map_include.patch"]` 让 p4a 在解压 numpy
  源码后自动应用 `<unordered_map>` include 补丁。其他内容与内置 recipe 逐行相等。
- **谁引用**：`buildozer.spec` 的 `p4a.local_recipes = /home/hydrogen/src/
  ReversibleMosaic/scripts/p4a_local_recipes`（rsync 到 WSL 后的路径）。
- **改动指引**：等 p4a 或 numpy 上游修复此 include 后可删；届时把 `patches` 那行
  去掉即可（其他部分不动，或让 recipe 完全回退到内置版本）。

#### [`scripts/p4a_local_recipes/numpy/patches/numpy_unordered_map_include.patch`](../scripts/p4a_local_recipes/numpy/patches/numpy_unordered_map_include.patch)
- 标准 unified diff (`-p1`)，只在
  `numpy/_core/src/multiarray/unique.cpp` 加一行 `#include <unordered_map>`。

### 运行前置

- 所有 `wsl_*.sh` 需要 WSL 里已就绪：
  - `~/.venvs/reversible-mosaic-build/`：装了 `buildozer` + `cython` 的 venv
  - `~/vendor/python-for-android/`：p4a 源码 checkout；`buildozer.spec` 里
    `p4a.source_dir` 引用它
  - `~/.buildozer/android/platform/android-ndk-r25b/`：手动放置的 NDK r25b
- 不要在 Windows Git Bash 直接跑 `.sh`（路径混用会 boom）。

---

## 配置

### [`buildozer.spec`](../buildozer.spec)
- **作用**：Android 打包配置。
- **当前状态**（阶段 0 探针 v6，Cython 已接入 setup.py）：
  - `title = ReversibleMosaic` / `package.name = reversiblemosaic` /
    `package.domain = io.placeholder`
  - `source.include_exts = py,pyx,kv,png,jpg,jpeg,json,md,ttf,ttc,txt`
    —— 加 `pyx` 让 Cython 源码进 tarball（p4a 会 cythonize 编译）
  - `source.exclude_dirs = .git,.venv,.idea,tests,artifacts,build,bin,.buildozer,docs,vendor,scripts`
    —— 加 `scripts` 让构建脚本 + p4a 本地 recipe 不进 APK
  - `version = 0.1.0`
  - **`requirements = python3,kivy,pyjnius,numpy,pillow,cython`** —— v6 追加
    `cython`；p4a 的 cython recipe `install_in_hostpython=True`，只在构建机装
  - `orientation = portrait`
  - `android.api = 34` / `android.minapi = 26` / `android.ndk = 25b`
  - `android.archs = arm64-v8a`
  - `android.private_storage = True`
  - `android.logcat_filters = *:S python:D SDL:D SDLActivity:D AndroidRuntime:E`
  - **`p4a.setup_py = 1`** —— v6 打开；让 buildozer 传 `--use-setup-py`
    给 p4a，触发 `pip install --no-deps -e .` 进而调 `setup.py::cythonize()`
    把 `reversible_mosaic/core/algorithm/v1.pyx` 编成 arm64 `.so`
  - **`p4a.local_recipes = /home/hydrogen/src/ReversibleMosaic/scripts/p4a_local_recipes`**
    —— v6 打开；覆盖 p4a 内置的 numpy recipe 以自动应用
    `<unordered_map>` include 补丁（NDK r25b clang-14 + libc++ 传递包含缺失）
  - `p4a.source_dir = /home/hydrogen/vendor/python-for-android` —— 指向本地
    p4a checkout；跳过 pip 装 p4a
- **改动指引**：
  - 加 requirement 后**不要**一次加多个；每次加一个（或一小批同类）跑一次探针，出问题好定位。
  - `package.domain = io.placeholder` 只是探针占位；发布前要换成正式域名。
  - 生产发布还需要 signing 配置（keystore 路径、alias、密码 —— **绝不
    入库**）。

### [`setup.py`](../setup.py)
- **作用**：v6 引入。项目根的最小 setuptools 钩子，只负责让
  `Cython.Build.cythonize()` 把 `reversible_mosaic/core/algorithm/v1.pyx`
  编成扩展模块。项目元数据 (name/version/deps) 全部走 `pyproject.toml`。
- **PC 行为**：`sys.platform == "win32"` 时跳过（`.pyx` 里的
  `__uint128_t` 是 GCC/clang 扩展，MSVC 没有）；PC dev 依旧走
  `reference_v1` 纯 Python 参考实现。
- **Android 行为**：p4a 用 `--use-setup-py` 触发 `pip install -e .`
  → `cythonize()` → cross-compile `.pyx` → 得到
  `reversible_mosaic/core/algorithm/v1.cpython-<abi>-aarch64-linux-android.so`
  → `import reversible_mosaic.core.algorithm.v1` 装机后可用。
- **override**：设 `REVERSIBLE_MOSAIC_BUILD_CYTHON=1` 强制打开、`=0` 强制关闭。
- **改动指引**：加新 .pyx 文件：在 `CYTHON_MODULES` 列表里追加路径即可。

### [`pyproject.toml`](../pyproject.toml)
- PEP 621 项目配置：`[project]` 的 name/version/dependencies；
  `[project.optional-dependencies].app` 里包含 `kivy` / `kivymd` 等
  desktop dev 依赖；`[tool.ruff]` / `[tool.mypy]` / `[tool.pytest]` 严格
  模式。
- **改动指引**：PC dev 环境用 `pip install -e '.[app]'`；`.[dev]` 有
  ruff/mypy/pytest/hypothesis 等。改 `[project].version` 时同步
  `__init__.py` 与 `buildozer.spec`。

### [`requirements-dev.lock`](../requirements-dev.lock)
- pip freeze 输出，锁定 PC dev 依赖版本。给 CI/新机器用来复现环境。

### [`.gitignore`](../.gitignore)
- 排除 `.venv/`、`.buildozer/`、`bin/`（APK 产物）、`.mypy_cache/` 等。
  **不要**把 `bin/` 从忽略里拿出来 —— APK 是构建产物，靠 SHA-256 追踪即可。

---

## 计划与文档（`docs/`）

- [`docs/algorithm-v1.md`](algorithm-v1.md)：V1 算法规范（冻结前的草稿）。
- [`docs/build-android.md`](build-android.md)：Android 构建说明（p4a
  recipe、NDK 布局、镜像用法）。
- [`docs/probe-report.md`](probe-report.md)：性能/质量探针数据；阶段 3 冻结
  时会把 1920×1080 真机耗时/内存写入。
- [`docs/source-index.md`](source-index.md)：**本文件**。

根目录的 [`development_plan.md`](../development_plan.md) 是**执行基线** —— 阶段
进度、障碍/对策、待办都写在那里；每完成一个可验证节点更新一次。

---

## 快速改动查询表

| 想做什么 | 该开哪个文件 |
|---------|---------------|
| 加/改一屏 UI | `reversible_mosaic/app.py`（KV 字符串 + Screen 类） |
| 改分享码规则 | `reversible_mosaic/domain/share_code.py` |
| 加任务状态 | `reversible_mosaic/domain/task_state.py`（记得同步 test） |
| 调整资源上限 | `reversible_mosaic/domain/limits.py`（同步 `docs/algorithm-v1.md`） |
| 改 V1 算法字节输出 | `algorithm/reference_v1.py` + 重跑 `tests/vectors/generate_v1_vectors.py` |
| 加 V2 算法 | 新建 `algorithm/reference_v2.py` + `registry._register_builtin_versions` |
| 加 pipeline stage | `core/pipeline.py` 常量 + `core/task_coordinator._sync_state_to_stage_locked` |
| 改进度回调粒度 | `domain/tasks.py::ProgressReporter` |
| 加 PNG 元数据字段 | `io/png_metadata.py`（保持向后兼容） |
| 加拒绝理由 | `io/probe.py` 或 `io/normalize.py`（同步 `tests/adversarial/`） |
| 加平台能力 | `android/gateways.py` Protocol + 两个实现（`desktop.py` + 未来的 Android 实现） |
| 改 view model | `ui/view_models.py`（**不要**在这里 import kivy） |
| 调整 Android 打包 | `buildozer.spec`（加依赖时一次一个） |
| 改构建脚本 | `scripts/wsl_build_android.sh`（**保留 rsync incremental**） |
| 加 p4a recipe / 换 recipe 版本 | 更新 `scripts/wsl_prefetch_p4a.sh` 的 RECIPES 数组 + 重跑一次 |
| 诊断 GitHub / 镜像可达性 | `scripts/probe_mirrors.sh` / `probe_git_mirrors.sh` |
| 加/改字体 | `reversible_mosaic/assets/fonts/` + `app.py` 里 `_CJK_FONT_PATH` |
| 加/改阶段 0 真机探针 | `reversible_mosaic/ui/self_test.py` 的 `SYNC_PROBES`；测试同步在 `tests/unit/test_self_test_probes.py` |
| 加/改 Cython .pyx 模块 | 新增 `.pyx` → 追加到 `setup.py::CYTHON_MODULES` → PC 侧跑 `python setup.py build_ext --inplace`（非 MSVC）→ WSL 侧 v6+ 自动 cross-compile |
| 覆盖 p4a 内置 recipe（打补丁、换版本） | `scripts/p4a_local_recipes/<name>/__init__.py` + `patches/`；`buildozer.spec` 已配 `p4a.local_recipes` 指向它 |

---

## 术语与约定

- **P0**：本轮 MVP 支持的输入子集（8-bit RGB/RGBA PNG，8-bit RGB JPEG）。
- **Share code**：用户手动记的分享代码。默认 `500000`；1–10 位 ASCII 十进
  制。空字符串 = 使用默认。
- **Round**：算法轮数。允许 `{1, 5, 10, 20}`；默认 5。
- **Stage**：pipeline 的可观察阶段 —— `normalize` / `transform` / `write`。
- **State**：任务状态机 10 态；由 `domain/task_state.py` 管控迁移。
- **Cancel token**：`threading.Event` 包装的协作取消标志；只在算法轮之间
  检查，不进 Cython nogil 段。
- **Gateway**：平台适配 Protocol（Android / desktop 各一份实现）。
- **Fixed vector**：`tests/vectors/vectors.json` 里的算法输出黄金参考；
  跨平台跨版本比对的锚点。
- **【联合】节点**：脚本自动化 + 用户手动一步的合作点（例如真机侧载 APK）。
- **【人工协助】节点**：需要用户在真实设备/视觉判断/发布身份上做主的节点。
