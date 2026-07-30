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
- **作用**：Kivy 应用外壳；阶段 2a 起为生产版本。纯 Kivy（无 kivymd）；
  `LabelBase.register(name="Roboto", fn_regular="assets/fonts/wqy-microhei.ttc")`
  在 import 阶段把默认字体替换成覆盖 Latin+CJK 的 wqy-microhei。
  `ScreenManager` 挂 7 个屏：
  `home` / `tutorial` / `encode` / `decode` / `progress` / `result` / `self_test`。
- **关键 export**：`ReversibleMosaicApp(App)`、`HomeScreen(Screen)`、
  `TutorialScreen(Screen)`。Encode/Decode/Progress/Result 屏从
  [ui/screens.py](../reversible_mosaic/ui/screens.py) 导入；SelfTestScreen 从
  [ui/self_test.py](../reversible_mosaic/ui/self_test.py) 导入。`_KV` 内嵌
  home/tutorial 的 KV markup。
- **App 状态**（`ReversibleMosaicApp` 实例属性）：
  - `encrypted_form_state: TaskFormState` / `restored_form_state: TaskFormState`
    — encode/decode 两个屏各自独立的表单状态，跨屏返回时保留。
  - `last_result: ResultSnapshot | None` / `last_operation: str | None`。
  - `_coordinator: TaskCoordinator | None` — lazy 单例；`schedule_on_main`
    绑定到 `Clock.schedule_once`，所有回调都桥回主线程。
  - `_output_gateway` / `_clipboard_gateway`（Stage 2b）— lazy 单例；
    Android 走 `native.AndroidOutputGateway/AndroidClipboardGateway`，
    PC 退回 `desktop.DesktopOutputGateway` + `_DesktopKivyClipboardGateway`
    （Kivy Core Clipboard 兜底）。
- **App 方法**：
  - `on_start()`（Stage 2b）— Kivy 生命周期钩子，跑 `cleanup_orphan_pending()`
    清 MediaStore 孤儿 pending 行。
  - `open_encode()` / `open_decode()` — 首页按钮的目标。
  - `launch_pipeline(operation, form)` — 用 `output_naming.compute_output_name`
    计算 `<原名>_mosaic.png` / `_reversal_mosaic.png`（重名 `_1/_2`），
    构造 `TaskRequest`、切到 progress 屏、启动 coordinator；输出落
    `{user_data_dir}/outputs/`（app 私有缓存）。
  - `cancel_pipeline()` — 转发到 coordinator。
  - `copy_share_code_to_clipboard(text)`（Stage 2b）— 通过
    `_clipboard_gateway_instance()` 调 `copy_sensitive(text)`。Android 13+
    自动 flag EXTRA_IS_SENSITIVE。
  - `save_current_result()`（Stage 2b）— worker 线程调
    `output_gateway.publish_png(source, display_name)`，成功回调
    `_on_saved(handle)` 更新 `last_result.saved_handle`；失败回调
    `_on_save_failed(message)` 写 `last_result.save_error`；两者都调
    `_get_result_screen().refresh_from_app()`。
  - `view_current_result()` / `share_current_result()`（Stage 2b）— 转发到
    `gateway.open_for_view(saved_handle)` / `gateway.share(handle, subject)`。
    subject 恒定为 `"ReversibleMosaic 输出"`，**不包含**分享代码。
  - `_on_progress` / `_on_completed` / `_on_failed` / `_on_cancelled` —
    coordinator 回调；这些已经在主线程上，可以直接摸 widget。
- **改动指引**：
  - 加新屏：在 `_KV` 里加 `<NewScreen>: name: "xxx"` block（若走 KV）+
    在 `ScreenManager` 加子节点 + Python 侧写 `NewScreen(Screen)` 类；
    或复用 `ui/screens.py` 的 programmatic pattern，在那里加类然后 import + 注册。
  - 加新的平台 gateway：改 `_build_output_gateway` / `_build_clipboard_gateway`
    工厂函数（Android 走 `native.py`，PC 走 `desktop.py`）。
  - 改字体：改 `_CJK_FONT_PATH` 和 `LabelBase.register` 的 name 参数。
  - **不要**在这里做像素处理 —— 屏只消费 view model，处理走 worker 线程。
  - **不要**在 coordinator 回调外触碰 widget —— 所有更新都必须在
    `Clock.schedule_once` 或 `on_pre_enter` 里，否则跨线程会崩。

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
- **作用**：P0 资源阈值（输入 50 MiB、边长 12288、总像素 50M、宽高比 64:1、
  JPEG segment 1 MiB、PNG 文本累计 64 KiB、内存 60% 上限）。给出无需分配的
  预算估算。历史：初始 12M → 20M（2026-07-29，覆盖 12MP 相机原图）
  → 30M / 边长 12288（2026-07-30 v13→v14，覆盖 24MP 直出与中度全景）
  → **50M**（2026-07-30 v14→v15 三次修订，覆盖 48–50MP 主流旗舰主档；
  4 GB Android 已淘汰，内存预算按 6–8 GB 中端下限）。
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
  V1 定稿版本每轮**只调 1 次**（单 neighborhood_swap pass 前）；
  Cython v1.pyx 释放 GIL 期间不查取消，需要主循环外套 checkpoint。

### [`domain/output_naming.py`](../reversible_mosaic/domain/output_naming.py)
- **作用**：Stage 2b 引入。**平台无关的输出文件名计算器**。给定原图 display
  name + 操作类型（encrypt/decrypt），返回 `<stem>_mosaic.png` 或
  `<stem>_reversal_mosaic.png`，重名时通过外部 `name_taken(candidate)` 谓词
  回调询问并递增 `_1/_2/...`。
- **常量**：`_ENCRYPT_SUFFIX = "_mosaic"`、`_DECRYPT_SUFFIX = "_reversal_mosaic"`、
  `_MAX_STEM_BYTES = 96`（UTF-8 字节安全截断）、
  `_UNSAFE_RE = r'[<>:"/\\|?*\x00-\x1f]'`。
- **导出**：
  - `sanitize_stem(raw: str) -> str` —— 替换保留字符 → `Path.stem` 去扩展名
    → 合并空白 → 截断到 96 字节。**先替换后 Path 解析**，否则 `/` 会被
    `Path` 当分隔符吃掉，`../etc/passwd` 就变成空串。
  - `compute_output_name(original_display_name, *, operation, name_taken=None,
    max_attempts=999) -> str` —— 主入口。`name_taken` 是谓词回调，同时用于
    filesystem check（`(cache_dir / name).exists()`）和 MediaStore check
    （`_media_store_has_name(...)`）。`original_display_name` 是 None 或
    空字符串时走时间戳 fallback：`mosaic_yyyymmdd_hhmmss.png` /
    `reversal_mosaic_yyyymmdd_hhmmss.png`。
- **谁用它**：`app.py::launch_pipeline` 计算 cache 文件名；`native.py`
  MediaStore save 复用同一 base 名再自查重（跨 cache & gallery 两处）。
- **改动指引**：
  - 加新的操作类型（比如 P1 加强模式）→ 在 `_base_stem` 里加 `elif`。
  - 修改保留字符集：更新 `_UNSAFE_RE` 并跑 `test_output_naming.py` 全套。
  - 不要在这里 import Kivy 或 numpy —— 纯领域逻辑，pytest 直测。

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

V1 参考实现 + Cython 优化候选。**V1 状态：FROZEN（2026-07-30）**。
`docs/algorithm-v1.md` 已翻 `FROZEN`，`tests/vectors/algorithm_v1.json`
`status: frozen`。V1 一个字节都不能改；行为变化必须新增 V2。

### [`algorithm/contracts.py`](../reversible_mosaic/core/algorithm/contracts.py)
- **作用**：算法边界契约 —— 类型、模式、轮数集合、异常类、像素校验。
- **导出**：
  - 类型：`PixelMode = Literal["RGB", "RGBA"]`、
    `PixelArray = npt.NDArray[np.uint8]`。
  - 常量：`VALID_ROUNDS = frozenset({2, 5, 15, 30})`（2026-07-29 二次修订，
    原 `{1, 5, 10, 20}`；1 轮位移 <3% 对真实照片视觉不到位，改为 2 起）。
  - 异常：`AlgorithmError(ValueError)`、`CancellationRequested(RuntimeError)`。
  - Protocol：`CancellationProbe`（`__call__() -> bool`）。
  - 数据类：`ImageSpec(width, height, mode)`（含 `channels` 属性）。
  - 函数：`validate_pixels(pixels, spec)` —— 检查 dtype/shape/C-contiguous。
- **谁用它**：`reference_v1.py`、`registry.py`、`pipeline.py`、`normalize.py`。
- **改动指引**：`VALID_ROUNDS` 是需求冻结项，同步改需求档 §5 / FR-ENC-001 /
  FR-DEC-005 / §12.2 / AC-005 与 `png_metadata._validate` 里的 rounds 检查。

### [`algorithm/registry.py`](../reversible_mosaic/core/algorithm/registry.py)
- **作用**：版本 registry。模块加载时 `_register_builtin_versions()` 会自动
  注册 V1，指向 `reference_v1.encrypt / decrypt`。**阶段 1 v6→v7**：现在
  优先尝试 `optimized_v1`（Cython 后端），失败退回 `reference_v1`。
- **类型别名**：`Transform = Callable[[PixelArray, int, int, CancellationProbe | None], PixelArray]`。
- **导出**：
  - `AlgorithmDescriptor(version, display_name, release_date, encrypt, decrypt)`
    冻结数据类。
  - `register(descriptor)`、`get(version) -> AlgorithmDescriptor`、
    `supported_versions() -> tuple[...]`（版本号倒序）、
    `latest() -> AlgorithmDescriptor`。
  - `v1_implementation() -> str`：返回 `"cython"` 或 `"reference"`；
    自检屏 / 测试可查当前活跃后端。
- **谁用它**：`core/pipeline.py::process_image` —— 加密调 `latest()`，解密调
  `get(algorithm_version or latest().version)`。
- **改动指引**：
  - **加 V2**：新建 `reference_v2.py`，在 `_register_builtin_versions()` 追加
    `register(AlgorithmDescriptor(version=2, ..., encrypt=..., decrypt=...))`。
    `latest()` 会自动返回 V2。
  - **换 V1 后端**：改 `_resolve_v1_transforms()` 里的 try/except；两个
    实现的 encrypt/decrypt 签名必须完全等同。

### [`algorithm/reference_v1.py`](../reversible_mosaic/core/algorithm/reference_v1.py)
- **作用**：V1 参考实现，"规范代表"。**2026-07-29 定稿**为**纯位置置换**
  算法（去除了旧草案的 lift + diffuse 色彩变换）。纯 Python 嵌套循环慢
  但可读，是固定向量 (fixed vectors) 的 ground truth。
- **常量**：
  - `_DOMAIN = b"reversible_mosaic/algorithm/v1\x00"`（域分离标签）
  - `_MASK64 = (1 << 64) - 1`
  - `_RADIUS_MIN = 8`、`_RADIUS_DIVISOR = 32`（半径公式参数）
  - `_SWAP_DOMAIN = 0x22`（置换阶段密钥标签）
- **内部函数**（下划线开头，不外部导出）：
  - `_splitmix64(value)` —— PRF，来自 splitmix64 家族。
  - `_derive_words(spec, seed) -> tuple[K0, K1, K2, K3]` —— SHA-256 派生
    4 个 64-bit word。V1 仅用 `words[1]`；其他 3 个保留给未来 P1
    色彩变换。
  - `_round_key(word, round_index, domain)` —— 每轮子密钥。
  - `_checkpoint(cancel)` —— 取消 probe，抛 `CancellationRequested`。
  - `_radius_for(width, height) -> int` —— `max(8, min(W, H) // 32)`。
  - `_neighborhood_swap_forward(pixels, key, radius)` —— 单轮正向扫描，
    canonical direction (只当 `j > i` 时交换)。
  - `_neighborhood_swap_inverse(pixels, key, radius)` —— 反向扫描；同一
    PRF、同一 canonical 判定，因 swap 自逆而抵消正向。
  - `_validate(pixels, rounds) -> ImageSpec` —— 轮数/模式/形状校验。
- **导出**：
  - `encrypt(pixels, seed, rounds, cancel=None) -> PixelArray`
  - `decrypt(pixels, seed, rounds, cancel=None) -> PixelArray`
- **每轮结构**：encrypt 只做 `_neighborhood_swap_forward`；decrypt 反向
  按 `range(rounds - 1, -1, -1)` 顺序做 `_neighborhood_swap_inverse`。
  **没有 lift、没有 diffuse** —— 那些代码保留在
  [`color_transform.py`](../reversible_mosaic/core/algorithm/color_transform.py)
  供 P1 加强模式使用。
- **关键性质**：调色板逐字节保留（只是位置改变，颜色值不动）；Alpha 随
  像素整体移动，从不被单独修改；`decrypt(encrypt(I)) == I` 逐字节相等。
- **谁用它**：`registry.py::_register_builtin_versions`、
  `optimized_v1.py` 导入 `_derive_words / _round_key / _validate /
  _checkpoint / _radius_for / _SWAP_DOMAIN`、
  `tests/unit/test_algorithm_v1.py`、`tests/property/test_algorithm_properties.py`、
  `tests/vectors/generate_v1_vectors.py`、`tests/vectors/test_v1_vectors.py`。
- **改动指引**：**冻结前**只允许改字节输出如果同时更新固定向量文件。
  冻结后（`docs/algorithm-v1.md` 状态翻 frozen）一个字节都不能动，改动 =
  破坏跨版本可逆性。加参数/半径公式变化必须新增 V2。

### [`algorithm/v1.pyx`](../reversible_mosaic/core/algorithm/v1.pyx)
- **作用**：Cython 优化候选，把 `reference_v1.py` 的
  `_neighborhood_swap_forward / _neighborhood_swap_inverse` 用 memoryview +
  `nogil` 重写。跟 Python 版**每个字节一致**（同样的 splitmix64 常量、
  同样的扫描顺序、同样的 canonical direction 判定）。**2026-07-29 定稿**：
  从 6 个 inner 函数（lift/permute/diffuse × forward/inverse）**精简到
  2 个**（neighborhood_swap × forward/inverse）。
- **导出**（`cpdef`）：
  - `neighborhood_swap_forward(pixels, key, radius)` —— `pixels: uint8_t[:, :, ::1]`
  - `neighborhood_swap_inverse(pixels, key, radius)`
- **状态**：Windows PC 无法编译；Linux/WSL 可通过 `setup.py build_ext
  --inplace` 或 `scripts/wsl_generate_visual_review.sh` 得 `.so`；
  Android arm64 通过 `scripts/wsl_build_v1_cython.sh` 交叉编译进 APK。
- **谁用它**：**阶段 1 已接入生产**：`registry.py` 通过 `optimized_v1.py`
  优先使用 Cython；PC/CI 无 Cython 时自动退回 `reference_v1`。
- **改动指引**：
  - `.pyx` 修改后必须重新编译（PC: `setup.py build_ext --inplace`；
    Android: 重跑 `scripts/wsl_build_v1_cython.sh`）。
  - Cython 内 `with nogil:` 段不能碰 Python 对象，也不能调 `_checkpoint`
    —— 取消检查只能在 Python 侧主循环（每轮之间，`optimized_v1.py` 里做）。
  - **必须保证与 `reference_v1.py` 逐字节一致**，
    `tests/unit/test_optimized_v1.py` 在 Linux/WSL 强制这条。

### [`algorithm/optimized_v1.py`](../reversible_mosaic/core/algorithm/optimized_v1.py)
- **作用**：阶段 1 引入，2026-07-29 定稿版本。Cython 后端的
  encrypt/decrypt 薄包装：从 `reference_v1` 导入
  `_derive_words / _round_key / _validate / _checkpoint / _radius_for /
  _SWAP_DOMAIN`，把 `_neighborhood_swap_forward/inverse` 的调用换成
  `v1.pyx` 的 Cython 版本。**保证与 `reference_v1` 逐字节一致**。
- **导出**：`encrypt(pixels, seed, rounds, cancel=None) -> PixelArray`、
  `decrypt(pixels, seed, rounds, cancel=None) -> PixelArray`、
  `CYTHON_MODULE_PATH: str`（Cython `.so`/`.pyd` 的路径，诊断用）。
- **模块导入**：`from ... import v1 as _cy` 在模块顶层；Cython 模块
  不存在时直接抛 `ImportError` —— `registry.py::_resolve_v1_transforms` 里
  的 try/except 负责兜底到 reference。
- **谁用它**：`registry.py` 优先注册 V1 时；`test_optimized_v1.py` 直接跨实现比对。
- **改动指引**：
  - **绝不**在这里做与 `reference_v1` 有差异的编排步骤 —— 一致性是唯一存在理由。
  - Alpha 通道行为完全由 Cython inner 保证；PY 侧不做额外处理。

### [`algorithm/color_transform.py`](../reversible_mosaic/core/algorithm/color_transform.py)
- **作用**：**2026-07-29 新增，P1 未来加强模式候选**。保留原 V1 草案的
  lift + diffuse 色彩变换代码（三角 lifting + 反馈链扩散），**不接入
  MVP 生产路径**。V1 已定稿为纯位置置换（不改变调色板）；此模块存在的
  唯一意义是"如果 P1 上线可选加强模式，代码路径已备好"。
- **导出**：
  - `lift_forward(flat, key)` / `lift_inverse(flat, key)` —— RGB 三角
    lifting（`r += 3g + 5b + m0`）；Alpha 完全不参与。
  - `diffuse_forward(flat, key, reverse)` / `diffuse_inverse(flat, key,
    reverse)` —— 反馈链扩散；`reverse=True` 走反向扫描。
- **状态**：**不被任何生产代码 import**。仅代码保留，不参与测试。
- **改动指引**：
  - P1 加强模式若上线：新增 `optional_encrypt(pixels, seed, rounds, cancel,
    color_transform=True)` 类型的入口；不要改动 V1 主流程。
  - 若 P1 一直不落地，可以在 V2/V3 时代整体删掉。

### [`algorithm/quality.py`](../reversible_mosaic/core/algorithm/quality.py)
- **作用**：阶段 1 引入。§12.3.3 三项视觉质量指标的实现，只依赖 numpy。
- **导出**：
  - `QualityMetrics(pixel_change_rate, horizontal_correlation,
    vertical_correlation, diagonal_correlation, edge_similarity)`
    冻结数据类；`as_dict()` 打平成可 JSON 化字典。
  - `pixel_change_rate(source, scrambled) -> float` —— 只统计 RGB 通道
    的字节级差异比例，Alpha 忽略。
  - `adjacent_pixel_correlations(pixels) -> (h, v, d)` —— 水平/垂直/对角
    亮度 Pearson 相关性（`ITU-R BT.601` luma 权重 0.299/0.587/0.114）。
  - `edge_similarity(source, scrambled) -> float` —— Sobel 边缘图
    二值化后 Jaccard 相似度；阈值 = max(50, mean(gradient magnitude))。
  - `compute_metrics(source, scrambled) -> QualityMetrics` —— 一次算齐 5 项。
- **谁用它**：`scripts/generate_visual_review_set.py` 每张打码结果算一次；
  `tests/unit/test_quality.py` 覆盖恒等/全变/纯色/RGBA/scrambled 场景。
- **改动指引**：
  - 阈值最终写进 `docs/algorithm-v1.md` 附录（阶段 1 冻结后）。
  - Sobel 阈值调整前要跑 20 张固定图集验证：太严会把纯色/低对比图错报为通过。

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

抽象接口 + 两个实现：PC 侧 desktop stubs + Android 侧 PyJNIus 实现。**Stage 2b
起 Android 端两个 gateway（MediaStore + Clipboard）合并在同一个 `native.py`
里**，跟 `desktop.py`（三个 desktop stub gateway）对称。

### [`android/gateways.py`](../reversible_mosaic/android/gateways.py)
- **作用**：三个 `Protocol`（结构类型）定义业务与平台的边界。
- **导出**：
  - `InputGateway`：`import_to_cache(uri, cache_dir) -> Path` —— 把选中 URI
    的字节安全复制到 app 私有缓存。
  - `OutputGateway`：`publish_png(source, display_name) -> str` /
    `open_for_view(handle)` / `share(handle, subject)`。
  - `ClipboardGateway`：`copy_sensitive(text)` —— 分享码复制且尽量标"敏感"。
- **谁用它**：`reversible_mosaic/app.py::_build_output_gateway` /
  `_build_clipboard_gateway` 里的平台选择器；`ui/screens.py` 只依赖协议。
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

### [`android/native.py`](../reversible_mosaic/android/native.py)
- **作用**：Stage 2b 引入。**Android 端所有 gateway 的具体实现**，走 PyJNIus。
  两个 gateway 合并在一个文件里是因为它们共用同一个平台边界（jnius autoclass、
  Android SDK 类）和加载门（`is_available()` 检查 jnius 是否可 import），分开
  维护会重复 JNI 帮手函数（`_autoclass` / `_python_activity` / `_api_level` /
  `_string_array`）。
- **顶层导出**：
  - `is_available() -> bool` —— PyJNIus 可 import 才返回 True；`app.py` 用它
    决定装 Android gateway 还是 desktop stub。
  - `AndroidMediaStoreError(RuntimeError)` —— MediaStore 相关失败的公共基类。
  - `AndroidOutputGateway` / `AndroidClipboardGateway`。
- **`AndroidOutputGateway`**（实现 `OutputGateway` 协议）：
  - `publish_png(source: Path, display_name: str) -> str` ——
    1. `_unique_display_name` 在 API 29+ 查询 MediaStore 增量 `_1/_2` 避重名；
    2. `insert()` 到 `Pictures/ReversibleMosaic`，API 29+ 加 `IS_PENDING=1`；
    3. `openOutputStream` 流式拷贝源字节；
    4. `_verify_media_store_bytes` 重新读一遍做 SHA-256 复读校验；
    5. API 29+ `IS_PENDING=0`，API 26-28 广播 `ACTION_MEDIA_SCANNER_SCAN_FILE`；
    6. 任何一步失败都 `_safe_delete` 掉 pending 行（FR-SAVE-006 半文件保护）。
    返回 `content://media/external/images/media/<id>` URI 字符串。
  - `open_for_view(handle: str)` —— `Intent.ACTION_VIEW`。
  - `share(handle: str, subject: str)` —— `Intent.ACTION_SEND` +
    `EXTRA_STREAM` + `FLAG_GRANT_READ_URI_PERMISSION`；`subject` 只填 App 通用
    标识，**绝不放分享代码**（FR-ENC-006 / FR-SAVE-004）。
  - `cleanup_orphan_pending() -> int` —— App 启动时清 `IS_PENDING=1` 的孤儿行
    （FR-TASK-006 / §9.2 item 3）；只在 API 29+ 有 IS_PENDING 语义，API 26-28
    返回 0。所有失败被吞掉不阻塞启动。
- **`AndroidClipboardGateway`**（实现 `ClipboardGateway` 协议）：
  - `copy_sensitive(text: str)` —— `ClipboardManager.setPrimaryClip` +
    `ClipData.newPlainText`。API 33+ 在 `ClipDescription` 设
    `EXTRA_IS_SENSITIVE=true`（FR-ENC-007），系统 UI 复制预览会遮掉值。
    任何异常被吞掉，剪贴板是尽力而为的便利功能。
- **改动指引**：
  - 加新的 Android gateway（比如 InputGateway 的 Android 实现）→ 在**同一个**
    `native.py` 里加类；`is_available()` 门只在文件顶层出现一次。
  - **禁止**在这里做 numpy/pillow 操作 —— 平台层只负责 JNI 转发。
  - JNI 类必须 lazy 解析（在方法内 import `jnius`），保持模块在 PC 上可导入。
  - **PyJNIus 重载分辨陷阱**：`Intent.putExtra` / `ContentValues.put` 有大量
    重载，Python 原生 `int` / `Uri` 会引发 `JavaMethodResolutionError`。凡是
    涉及"多态入参"的调用一律用 `_cast(target_class, value)`（内部走
    `jnius.cast`）明确目标签名。当前落地点：`ContentValues.put("is_pending",
    Integer(0/1))`、`putExtra(EXTRA_STREAM, cast Parcelable uri)`、
    `putExtra(EXTRA_SUBJECT, cast CharSequence String)`。

### [`android/__init__.py`](../reversible_mosaic/android/__init__.py)
- 仅 docstring `"""Android platform adapters."""`。

---

## UI（`reversible_mosaic/ui/`）

### [`ui/view_models.py`](../reversible_mosaic/ui/view_models.py)
- **作用**：不依赖 Kivy 的表单/进度/结果 view model。屏在主线程持有实例，
  worker 通过 `TaskCoordinator` 回调更新。这样 view model 可以被
  pytest 直接测。
- **常量**：`VALID_ROUNDS = (2, 5, 15, 30)`、`DEFAULT_ROUNDS = 5`。
- **导出**：
  - `TaskFormState(operation, input_path=None, share_code="", rounds=5, algorithm_version=None, original_display_name=None)`：
    - `parsed_share_code() -> str | None` （抛 `ShareCodeError`）。
    - `randomize_share_code() -> None`。
    - `can_start() -> bool`（输入路径 + 合法 rounds + 合法 share_code）。
    - `algorithm_version` 只在 decode 用；encode 恒定用 `latest()`。
    - `original_display_name`（Stage 2b）— Photo Picker 或 PC 侧回传的原图
      文件名，用于生成 `<stem>_mosaic.png` 输出名。为 None 时走时间戳 fallback。
  - `ProgressSnapshot(stage, fraction, label)`：`from_stage(stage, fraction)`
    工厂方法把 pipeline stage 常量映射为中文标签（normalize→"规范化"，
    transform→"算法处理"，write→"写入 PNG"）。
  - `ResultSnapshot(output_path, algorithm_version, rounds, share_code_display,
    operation="encrypted", display_name="", saved_handle=None, save_error=None)`：
    - `from_pipeline(result, *, operation, display_name)` 工厂。
    - `operation`（"encrypted"/"restored"）决定 ResultScreen 是否显示分享码。
    - `display_name` — MediaStore 保存时用的 DISPLAY_NAME。
    - `saved_handle` — Android MediaStore URI 或 desktop 输出路径；None 表示
      结果仍在 app 私有缓存里，尚未 publish 到相册。
    - `save_error` — 上次保存失败的原因。
    - `is_saved` property = `saved_handle is not None`。
- **谁用它**：阶段 2a 的四个生产屏 [ui/screens.py](../reversible_mosaic/ui/screens.py)
  与测试 `tests/unit/test_view_models.py`。
- **改动指引**：不要在这里 import kivy 或 kivymd（会破坏 pytest 便捷跑测）。
  UI 只应该"读"这些 dataclass 的字段，不要把 Kivy widget 引用塞进来。

### [`ui/input_hint.py`](../reversible_mosaic/ui/input_hint.py)
- **作用**：阶段 2a 引入。用户选择输入图片后，屏调 `inspect_input(path)` 拿
  预览信息（尺寸、模式、格式、文件大小、元数据）。**尺寸限制在这一层就 enforce**
  ——`validate_dimensions(MAX_EDGE=12288 / MAX_PIXELS=50M / MAX_ASPECT_RATIO=64)`
  违反直接返回 `InputHint(is_ok=False, error=...)`，让 Start 按钮 disable。
  JPEG marker walk 之类的深度 preflight 仍在 `io.normalize` 才跑。
  历史：阶段 2b v11→v13 真机测试暴露 —— 之前把限制留给 pipeline 后期，
  超尺图片会走进"规范化"进度屏，用户无从得知；现在提前挡在选图那一步。
- **导出**：
  - `InputHint(path, format, width, height, mode, file_bytes, metadata, error)`
    冻结数据类；`.is_ok` / `.has_encrypted_metadata` /
    `.suggested_rounds` / `.suggested_algorithm_version` 便捷访问器。
  - `inspect_input(path) -> InputHint`：PNG 走 `io.probe.scan_png` +
    `png_metadata.parse_png_metadata`；JPEG 走 Pillow lazy header；其他
    后缀显式拒绝（`InputHint.error` 中给出中文原因）。
  - `format_file_size(bytes) -> str`：`"512 B"` / `"1.2 KB"` / `"2.34 MB"`。
- **谁用它**：`ui/screens.py` 的 `_EncodeDecodeBase._on_pick` 与
  `DecodeScreen._on_input_selected`（后者用元数据自动带入算法版本 + 轮数）；
  `tests/unit/test_input_hint.py` 8 case 覆盖。
- **改动指引**：新增支持格式时改 `inspect_input` 分支；预览失败不要抛异常，
  一律通过 `InputHint.error` 上浮。

### [`ui/file_picker.py`](../reversible_mosaic/ui/file_picker.py)
- **作用**：阶段 2a 引入，2b 完善为**双实现**。Android 侧走
  `Intent.ACTION_GET_CONTENT`（Android 13+ 自动映射到系统 Photo Picker）；PC
  侧用 Kivy `FileChooserListView` + `Popup` 兜底。异常时自动 fallback
  Kivy chooser，日志落 `{user_data_dir}/picker_error.log`。
- **类型别名**：`SelectionCallback = Callable[[Path, str | None], None]`。
  第二参数是原图 display name —— Android 侧通过
  `OpenableColumns.DISPLAY_NAME` 查 ContentResolver 拿到；PC 侧就是
  `chosen_path.name`。为 None 时下游走时间戳 fallback 命名。
- **导出**：`open_file_picker(on_selected: SelectionCallback) -> Any`。
  用户按 "使用此文件" 时以 `(cached_path, display_name)` 回调；"取消" 或
  点空处不回调。
- **改动指引**：切换到新的 Android picker（比如 Photo Picker 官方 API v2）
  时，保留 `SelectionCallback` 签名不变——`Screen._on_pick` 无需改动。

### [`ui/screens.py`](../reversible_mosaic/ui/screens.py)
- **作用**：阶段 2a 引入，2b 扩展 ResultScreen 到 save/view/share 流程。
  四个生产屏：
  - `EncodeScreen` / `DecodeScreen` — 共用 `_EncodeDecodeBase`：文件选择、
    轮数 Spinner、分享代码 TextInput + 随机 6 位 / 清除、开始按钮 disable
    直到 `TaskFormState.can_start()`。DecodeScreen 有算法版本 Spinner，
    且选文件后自动从 PNG 元数据带入 version + rounds。`_on_pick` 回调
    接受 `(cached_path, display_name)` 二元组，写入
    `form.original_display_name`（Stage 2b）。
  - `ProgressScreen` — 阶段标签、进度条（fraction 未知时 indeterminate）、
    已耗时秒表（`Clock.schedule_interval` 每 0.1s tick）、取消按钮。
    - **v13 修复**：`stage_label` / `detail_label` / `elapsed_label`
      StringProperty 通过 `self.bind(...)` 响应式同步到 widget `.text`；
      之前 `_on_failed` 只写 property 但 label 显示不变，看起来像卡死。
    - 取消按钮在 `coordinator.state == IDLE`（pipeline 已完成 / 失败）
      时降级为"返回首页"，避免失败后无出路。
  - `ResultScreen`（**Stage 2b 状态机**）——
    - **状态**：`unsaved` → `saved` / `save_error`。
    - **按钮组**：主行 `保存到相册 / 查看 / 分享`（后两个未保存前 disabled）；
      副行 `复制分享代码 / 返回首页`。
    - `_on_save()` 调 `app.save_current_result()`（worker 线程走 gateway.publish_png）。
    - `_on_view()` / `_on_share()` 调对应 app 方法；分享前必弹
      `_show_share_reminder`（FR-SAVE-005 "文件/原图 发送" 提示）。
    - `_on_back()` 未保存时弹 `_show_unsaved_confirmation`（FR-SAVE-007）。
    - `refresh_from_app()` 供 app 在保存成功/失败后调用，刷新按钮 disable 状态。
- **状态存放**：屏本身无长期状态；`app.encrypted_form_state` /
  `app.restored_form_state` / `app.last_result` / `app.last_operation`
  在 `ReversibleMosaicApp` 上，跨屏共享。
- **主线程边界**：所有屏方法只在 Kivy 主线程执行；worker 线程结果通过
  `TaskCoordinator.schedule_on_main = Clock.schedule_once` 转发。
- **改动指引**：
  - 加新表单字段：先在 `view_models.TaskFormState` 加字段 → 再在
    `_EncodeDecodeBase._build_widget_tree` 挂 widget → `_sync_form` 里回写。
  - 加 result 页新按钮：走 app 方法而不是直接摸 gateway，保持
    "worker/gateway 逻辑在 app.py，UI 只发信号 + 展示" 的分层。
  - 屏内不 import Kivy 之外的东西时可提到 `ui/view_models.py` 便于 pytest 直测。

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
| [`test_task_coordinator.py`](../tests/unit/test_task_coordinator.py) | `core/task_coordinator.py` | 成功/失败/取消/双启动/reset；Stage 3 Block 1 新增 8 case：cancel→reset→re-start、fail→reset→re-start、reset 在 mid-flight 被拒、IDLE reset noop、无回调仍完成、cancel-before-start noop、并发双 start 仅一次通过、progress 携带 stage + fraction（共 12 case） |
| [`test_view_models.py`](../tests/unit/test_view_models.py) | `ui/view_models.py` | 表单 can_start、progress 标签映射、Stage 2b 的 ResultSnapshot save 状态转换 |
| [`test_self_test_probes.py`](../tests/unit/test_self_test_probes.py) | `ui/self_test.py` | PC 端可跑的 4 个探针（numpy/pillow/reference_v1/v1_cython），pyjnius 探针在 PC 上应 ImportError |
| [`test_optimized_v1.py`](../tests/unit/test_optimized_v1.py) | `algorithm/optimized_v1.py` + `algorithm/v1.pyx` | reference vs Cython 逐字节比对；Windows 无 Cython 时整个模块 skip |
| [`test_quality.py`](../tests/unit/test_quality.py) | `algorithm/quality.py` | §12.3.3 三项指标：恒等/全变/纯色/RGBA/scrambled 各场景 |
| [`test_input_hint.py`](../tests/unit/test_input_hint.py) | `ui/input_hint.py` | PNG/JPEG/异常/元数据解析共 8 case |
| [`test_output_naming.py`](../tests/unit/test_output_naming.py) | `domain/output_naming.py` | Stage 2b: `_mosaic/_reversal_mosaic` 后缀、`_1/_2` 递增、reserved 字符 sanitize、Windows 路径注入防护 |
| [`test_desktop_gateways.py`](../tests/unit/test_desktop_gateways.py) | `android/desktop.py` | Stage 2b: 冲突计数、input gateway 导入；Stage 3 Block 1: 10 次冲突叠加、源文件缺失 raise、mid-copy IOError、目录懒创建、大小写扩展名归一化、相同源双次导入互不覆盖（共 11 case） |
| [`test_android_native.py`](../tests/unit/test_android_native.py) | `android/native.py`（JNI mock） | **Stage 3 Block 1 新增**：14 case。构造 gate 检查（jnius 缺失时 raise）；`publish_png` 失败注入 —— insert 返回 null、write IOError、SHA-256 mismatch、commit 抛错时**必删 pending 行**（FR-SAVE-006）；API 28 skip `_unique_display_name` query；`cleanup_orphan_pending` 在 API 28 / 异常 / null cursor 都返回 0（FR-TASK-006）；`copy_sensitive` 吞 JNI 异常（FR-ENC-007）。 |

### [`tests/property/test_algorithm_properties.py`](../tests/property/test_algorithm_properties.py)
- 用 Hypothesis 生成任意 `(w, h, mode, seed, rounds)`，断言
  `decrypt(encrypt(x)) == x`、确定性、Alpha 保守恒、5 项性质共 ~170 组样本。
### [`tests/property/`](../tests/property/)
- [`test_algorithm_properties.py`](../tests/property/test_algorithm_properties.py)：
  Hypothesis 生成 `(w, h, mode, seed, rounds)`，断言
  `decrypt(encrypt(x)) == x`、确定性、非平凡输出。
  2/5 轮走 80 例，15/30 轮走 12 例，是 V1 冻结前"打不同种子跑不出 bug"的主要防线。
  **Stage 3 Block 1 调整**：`test_v1_nontrivial_output_for_random_seeds`
  跳过阈值从 `pixels < 4 or unique_rgb < 3` 放宽到 `pixels < 9 or unique_rgb < 5`。
  V1 是纯位置置换 + palette preserve，极小图片（如 1×5 with 3 unique）在 canonical
  direction swap 下可能给出 byte-identical 输出，属于 §12.3.5 "低信息图片仅验收
  可逆性" 范围。

### [`tests/vectors/`](../tests/vectors/)
- [`generate_v1_vectors.py`](../tests/vectors/generate_v1_vectors.py)：合成
  固定图集，跑 2/5/15/30 轮，把 encrypt 输出的 hex/SHA-256 写入
  `algorithm_v1.json`（V1 冻结后正式化，2026-07-30；供跨平台比对）。
- [`test_v1_vectors.py`](../tests/vectors/test_v1_vectors.py)：读取
  冻结 JSON，断言 `reference_v1` **和** registry 当前后端（可能是 Cython）
  的输出与文件一致。这是"防意外修改 V1 字节输出"的兜底。
- **改动指引**：改 `reference_v1.py` 或 `v1.pyx` 后必须重跑
  `generate_v1_vectors.py` 更新固定向量；否则 `test_v1_vectors.py` 会红。
  冻结后重跑 = 破坏冻结。

### [`tests/adversarial/test_malicious_inputs.py`](../tests/adversarial/test_malicious_inputs.py)
- 恶意 PNG/JPEG + 元数据 fuzz 拒绝测试。所有失败路径都必须落回 `ImageProbeError`
  或 `MetadataStatus.INVALID` / `CONFLICT`，绝不允许崩溃或半文件泄漏。
- **Stage 3 Block 1 大幅扩展**（原 12 case → 58 case）：
  - **PNG chunk 深度 fuzz**（12 case）：chunk 长度越界、data 截断、CRC 错、
    IHDR 长度/深度/color_type/compression/filter 异常、双 IHDR、空文件、
    仅签名、超 50 MiB。
  - **元数据 schema fuzz**（20 case）：zTXt/iTXt 保留字拒收、value 超 2048、
    非 ASCII、schema_version=0/-1/2、错误 app_marker、未知 operation_type、
    非正整数 algorithm_version、旧轮次 `{1, 3, 10, 20, 100}` 拒收（防误接���
    pre-v14 元数据）、未知 pixel_mode、非正 width/height、缺 required field、
    字符串代 int、bool 代 int（Python bool 是 int 子类，靠 `type() is not int`
    严格拦截）、4 candidates → 重复 branch / 5 candidates → 过多 branch、
    无 null 分隔符、pixel_mode 冲突、serialize + parse 完整往返。
  - **JPEG 恶意样本**（4 case）：无 SOI、无 EOI 截断、超大 APP1、
    segment_length < 2。
  - **write_png 元数据往返**（1 case）：`write_png` → `scan_png` →
    `parse_png_metadata` 三跳还原验证。
- **改动指引**：新增拒绝理由时同步 `io/probe.py` 或 `io/png_metadata.py` 里对应
  的 `raise`，并追加 case 到对应分组。测试名前缀 `test_png_` / `test_metadata_`
  / `test_jpeg_` / `test_write_png_` 已按范围分开，加新 case 时保持归位。

---

## 构建 & 探测脚本（`scripts/`）

### 视觉验收 / 质量报告

#### [`scripts/generate_visual_review_set.py`](../scripts/generate_visual_review_set.py)
- **作用**：阶段 1 引入。读 `artifacts/visual_review_sources/` 下的固定图集，
  对每张跑 3 个种子 × 4 个轮数（**2/5/15/30**，2026-07-29 二次修订），走
  `registry.get(1)` 加密（因此会自动使用当前活跃后端 —— Cython 或 reference），
  产出结构化输出：
  - `artifacts/visual_review/<image_id>/source.png` —— 原图拷贝
  - `artifacts/visual_review/<image_id>/rounds_XX_seed_YY.png` —— 打码结果
    （含合法 `reversible_mosaic` tEXt 元数据 —— 结果可以直接被自动化恢复测试消费）
  - `artifacts/visual_review/metrics.json` —— 每张 × 每种子 × 每轮数的 5 项
    指标（像素变化率、水平/垂直/对角相邻相关性、边缘相似度）+ 按轮数/种子聚合的汇总
  - `artifacts/visual_review/scorecard.md` —— **单人 MVP 变体** 评分表模板
    （§12.3 单人验收偏差，2026-07-29 记录）
- **命令**：`python scripts/generate_visual_review_set.py --sources <input_dir>
  --output <output_dir>`。默认 `--sources artifacts/visual_review_sources
  --output artifacts/visual_review`。**每次执行会先 rmtree 输出目录**。
- **决定性**：同源图 + 同 registry 后端 → 逐字节一致输出。
- **PC 太慢**：纯 Python reference 实现在 12MP+ 图上 20 轮要几小时。用
  `scripts/wsl_generate_visual_review.sh` 在 WSL Linux 里跑 Cython 版，5-10
  分钟出所有 240 张 PNG。
- **改动指引**：
  - 加新种子：改 `CANONICAL_SEEDS` 顶层常量。
  - 加新轮数：改 `ROUNDS` 顶层常量 —— 但只能是 §7.3 `VALID_ROUNDS` = {2, 5, 15, 30}。
  - `scorecard.md` 模板文字属于用户输出，允许全宽中文标点（file-level
    `# ruff: noqa: RUF001`）。单人 MVP 变体已按 §12.3 偏差改造；若恢复
    3 人验收版本，参考 git history 里 stage2a 之前的模板。

#### [`scripts/wsl_generate_visual_review.sh`](../scripts/wsl_generate_visual_review.sh)
- **作用**：**在 WSL Ubuntu-24.04 里跑视觉验收生成脚本的完整封装**。因为
  Windows PC 编不出 Cython .so，PC 上跑 `generate_visual_review_set.py` 只能
  用 pure-Python reference 实现，对 12MP+ 图 20 轮要几小时。这个 shell 脚本
  一键完成：
  1. 确保 WSL 侧 dev venv 存在（`~/.venvs/reversible-mosaic-dev/`），装齐
     numpy / pillow / cython / setuptools
  2. rsync Windows 工作区到 `/home/hydrogen/src/ReversibleMosaic/`
  3. 交叉编译 Linux x86_64 `.so`（`REVERSIBLE_MOSAIC_BUILD_CYTHON=1 python
     setup.py build_ext --inplace`）
  4. 打印 `backend =` 确认 Cython 加载成功
  5. 调 `generate_visual_review_set.py` 传参
  6. rsync 输出目录（`artifacts/visual_review/`）回 Windows
- **命令**：`wsl -d Ubuntu -e bash /mnt/d/python/python_projects/ReversibleMosaic/scripts/wsl_generate_visual_review.sh`
  可选传参（会转发给 generator）：`--sources <dir>`, `--output <dir>`。
- **前置**：WSL Ubuntu-24.04 里安装 `python3-venv`（`sudo apt install
  python3-venv`）。首次运行会 `pip install` numpy/pillow/cython，需要网络。
- **一次性 vs 常用**：**常用**。视觉验收每次改 seed / rounds / R 都会重跑。
- **改动指引**：
  - venv 路径写死在脚本顶部 `VENV=...`，避免 `$VENV` 被展开成空字符串
    在 Windows 工作区意外创建 Linux 符号链接（曾经踩过坑）。
  - 若 Cython 编译失败，`build_ext` 会打印错误但脚本继续 —— 检查
    "backend =" 输出：`reference` 就是编译失败退回；`cython` 是成功。

### 主构建

> **⚠️ 打包必须走 [`scripts/wsl_build_android.sh`](../scripts/wsl_build_android.sh)，
> 不要手工在任意目录跑 `buildozer android debug`。**
>
> 手工方式的实测事故（2026-07-30，v15 打包）：直接 `cd /mnt/d/python/python_projects/ReversibleMosaic && buildozer android debug` 后 p4a 起的 `sh` 子进程变僵尸卡在网络阶段，主进程 0% CPU 挂死 52 分钟，`.buildozer/` build/dists/packages 三个子目录全空——**根本没进到编译**。
>
> 规范脚本做的事，手工方式全会漏掉：
> 1. `rsync -a --delete --exclude .buildozer/` 把源码同步到 WSL 原生盘
>    `/home/hydrogen/src/ReversibleMosaic/`，避开 /mnt/d 的 9P/DrvFs 挂死风险。
> 2. 从 `~/.p4a-source-cache/` hard-link tarball 到 workspace 里 `packages/`，让 p4a 全程跳网。
> 3. 通过 `GIT_CONFIG_COUNT/KEY_0/VALUE_0` 把 recipe 里 `github.com/*` clone
>    重定向到 `ghfast.top` 镜像（sdl2_image/sdl2_mixer/sdl2_ttf submodule clone 用得上）。
> 4. 先跑 [`scripts/wsl_build_v1_cython.sh`](../scripts/wsl_build_v1_cython.sh) 把 V1
>    Cython 内循环交叉编译成 arm64 `.so` 塞回源码树。
> 5. `tee` 日志到 `/home/hydrogen/src/reversible-mosaic-build.log`（不用 `| tail -20` 吞掉过程）。
>
> **正确调用**（PowerShell / Windows shell 里）：
>
>     wsl -d Ubuntu -e bash /mnt/d/python/python_projects/ReversibleMosaic/scripts/wsl_build_android.sh
>
> 产物在 **`~/src/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-debug.apk`**（WSL 原生盘），
> 手工 `cp ~/src/ReversibleMosaic/bin/*.apk /mnt/d/python/python_projects/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-debug-vNN.apk` 拷回 Windows 侧并附上版本号后缀，最后 `sha256sum` 记录哈希。

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
  - **`android.permissions = (name=android.permission.WRITE_EXTERNAL_STORAGE;maxSdkVersion=28)`**
    —— Stage 2b：MediaStore 保存在 API 26-28 需要 WRITE_EXTERNAL_STORAGE，
    API 29+ scoped storage 不需要，因此 `maxSdkVersion=28` 精准限定。
    **不申请**网络/位置/相机等权限（FR-TASK-007 / §11.3）。
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

- [`docs/algorithm-v1.md`](algorithm-v1.md)：V1 算法规范（**FROZEN 2026-07-30**，
  rounds {2, 5, 15, 30}, R=max(8, min(W,H)//32)）。**附录 A：面向读者的算法讲解**
  （A.1–A.12，2026-07-30 追加）给出直觉版说明 + ASCII 公式 + 可逆性直觉证明，
  是"想读懂 V1 在做什么"的入口，不覆盖 §1–5 的严格规范。
- [`docs/build-android.md`](build-android.md)：**Stage 3 Block 2 大改** ——
  阶段 0 草案升级为**阶段 3 冻结基线**。工具链版本（OpenJDK 17 / NDK r25b /
  target Python 3.14 / NumPy 2.3.0 / Pillow 11.3.0 / Cython 3.2.9）、Android
  目标（API 34 / minapi 26 / arm64-v8a）、一次性准备、增量构建、Cython 交叉
  编译时序、APK 版本后缀命名、签名策略、已知障碍与对策全部落地。所有工具链
  升级必须同步这份文档。
- [`docs/release-notes.md`](release-notes.md)：**Stage 3 Block 2 新增** ——
  v0.1.0 MVP 内部签名 Release 发行说明。§1 版本身份与限制（applicationId
  占位 + 内部自签 keystore + 正式发布五步走）；§2-4 功能/限制/已知问题；§5
  版本历史（Stage 0-3 全流程 + APK SHA-256 表格占位，Block 3 填充）；§6
  **第三方组件与许可清单**（APK 内 14 项 + PC dev + 构建工具）；§7-8 用户
  教程要点/支持反馈。
- [`docs/test-plan.md`](test-plan.md)：**Stage 3 Block 2 新增** —— 测试计划
  与 AC 追踪。§1 环境快照 + 冻结阈值；§2 AC-001~017 + AC-PERF 逐条 status
  标记；§3 覆盖率汇总（250 passed / 21 skipped）；§4 §12.3 单人偏差豁免记录；
  §5 Block 3/4 收官时追加的真机数据槽位。
- [`docs/probe-report.md`](probe-report.md)：性能/质量探针数据；阶段 3 冻结
  时会把 1920×1080 真机耗时/内存写入。
- [`docs/source-index.md`](source-index.md)：**本文件**。

根目录的 [`development_plan.md`](../development_plan.md) 是**执行基线** —— 阶段
进度、障碍/对策、待办都写在那里；每完成一个可验证节点更新一次。

---

## 快速改动查询表

| 想做什么 | 该开哪个文件 |
|---------|---------------|
| 加/改一屏 UI | 生产屏改 `reversible_mosaic/ui/screens.py`（programmatic UI）；home/tutorial 改 `reversible_mosaic/app.py` KV block |
| 加/改 view model 字段 | `reversible_mosaic/ui/view_models.py`（**不要**在这里 import kivy） |
| 加/改文件选择器 | `reversible_mosaic/ui/file_picker.py`（Android 走 Intent.ACTION_GET_CONTENT + ContentResolver display name 查询；PC 走 Kivy chooser） |
| 改分享码规则 | `reversible_mosaic/domain/share_code.py` |
| 加任务状态 | `reversible_mosaic/domain/task_state.py`（记得同步 test） |
| 调整资源上限 | `reversible_mosaic/domain/limits.py`（同步 `docs/algorithm-v1.md`） |
| 改 V1 算法字节输出 | `algorithm/reference_v1.py` + 重跑 `tests/vectors/generate_v1_vectors.py` |
| 加 V2 算法 | 新建 `algorithm/reference_v2.py` + `registry._register_builtin_versions` |
| 加 pipeline stage | `core/pipeline.py` 常量 + `core/task_coordinator._sync_state_to_stage_locked` |
| 改进度回调粒度 | `domain/tasks.py::ProgressReporter` |
| 加 PNG 元数据字段 | `io/png_metadata.py`（保持向后兼容） |
| 加拒绝理由 | `io/probe.py` 或 `io/normalize.py`（同步 `tests/adversarial/`） |
| 加平台能力 | `android/gateways.py` Protocol + 两个实现（`desktop.py` + `native.py`）；同类 Android gateway 全部集中在 `native.py` |
| 改 MediaStore 保存 / 分享 / 查看 | `reversible_mosaic/android/native.py::AndroidOutputGateway`（保留 `publish_png` / `open_for_view` / `share` 签名，`app.py` 无需改动） |
| 加 result 页新按钮 | `ui/screens.py::ResultScreen._build_widget_tree` 挂 widget → `app.py` 加对应方法（保持 gateway 调用集中在 app 层） |
| 改输出命名规则 | `domain/output_naming.py`（同步 `tests/unit/test_output_naming.py`）|
| 调整 Android 打包 | `buildozer.spec`（加依赖时一次一个） |
| 改构建脚本 | `scripts/wsl_build_android.sh`（**保留 rsync incremental**） |
| 加 p4a recipe / 换 recipe 版本 | 更新 `scripts/wsl_prefetch_p4a.sh` 的 RECIPES 数组 + 重跑一次 |
| 诊断 GitHub / 镜像可达性 | `scripts/probe_mirrors.sh` / `probe_git_mirrors.sh` |
| 加/改字体 | `reversible_mosaic/assets/fonts/` + `app.py` 里 `_CJK_FONT_PATH` |
| 加/改阶段 0 真机探针 | `reversible_mosaic/ui/self_test.py` 的 `SYNC_PROBES`；测试同步在 `tests/unit/test_self_test_probes.py` |
| 加/改 Cython .pyx 模块 | 新增 `.pyx` → 追加到 `setup.py::CYTHON_MODULES` → PC 侧跑 `python setup.py build_ext --inplace`（非 MSVC）→ WSL 侧 v6+ 自动 cross-compile |
| 加视觉质量指标 | `reversible_mosaic/core/algorithm/quality.py` 新增函数 + `tests/unit/test_quality.py` 断言；再改 `scripts/generate_visual_review_set.py` 输出到 metrics.json |
| 跑视觉验收样本 | 把源图放到 `artifacts/visual_review_sources/` → 执行 `python scripts/generate_visual_review_set.py`，产出会在 `artifacts/visual_review/` |
| 覆盖 p4a 内置 recipe（打补丁、换版本） | `scripts/p4a_local_recipes/<name>/__init__.py` + `patches/`；`buildozer.spec` 已配 `p4a.local_recipes` 指向它 |

---

## 术语与约定

- **P0**：本轮 MVP 支持的输入子集（8-bit RGB/RGBA PNG，8-bit RGB JPEG）。
- **Share code**：用户手动记的分享代码。默认 `500000`；1–10 位 ASCII 十进
  制。空字符串 = 使用默认。
- **Round**：算法轮数。允许 `{2, 5, 15, 30}`；默认 5。（2026-07-29 二次修订，
  原 `{1, 5, 10, 20}`）
- **Stage**：pipeline 的可观察阶段 —— `normalize` / `transform` / `write`。
- **State**：任务状态机 10 态；由 `domain/task_state.py` 管控迁移。
- **Cancel token**：`threading.Event` 包装的协作取消标志；只在算法轮之间
  检查，不进 Cython nogil 段。
- **Gateway**：平台适配 Protocol（Android / desktop 各一份实现）。
- **Fixed vector**：`tests/vectors/algorithm_v1.json` 里的算法输出黄金参考；
  跨平台跨版本比对的锚点。
- **【联合】节点**：脚本自动化 + 用户手动一步的合作点（例如真机侧载 APK）。
- **【人工协助】节点**：需要用户在真实设备/视觉判断/发布身份上做主的节点。
