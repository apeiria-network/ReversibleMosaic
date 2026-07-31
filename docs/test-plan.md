# 测试计划与 AC 追踪（阶段 3）

> **版本**：0.1.0（阶段 3 起草，2026-07-30）
> **对应需求档**：[`requirements_product_v1.md`](../requirements_product_v1.md) §12–§14
> **状态标记**：✅ 通过 / ⏳ 进行中 / ⏱ 待人工 / ❌ 未通过 / — 不适用

本文档汇总 MVP 交付前所有验收条款的证据。每条 AC 都对应：
- **执行方**：自动 / 人工 / 联合（AC 表标注见需求档 §13）
- **证据位置**：具体测试文件、脚本输出或人工签署单
- **状态**：当前进度

Stage 3 Block 3（Release APK + 真机验收）之前，联合类 AC 的人工部分暂
标 ⏱ 待人工；Block 4（AC 全表验收）结束后本文档整体升级为**测试报告**
交付物。

---

## 1. 环境快照

### 自动测试执行环境

- **主机**：Windows 11 Home + WSL2 Ubuntu 24.04
- **Windows Python**：CPython 3.11.9
- **pytest 版本**：9.1.1
- **hypothesis 版本**：6.161.2
- **mypy 版本**：1.20.2（strict 模式）
- **ruff 版本**：0.16.0

### 目标验收设备（AC-PERF、AC-016 人工部分）

- **性能验收设备（当前）**：小米 K80 Pro / Android 16 / RAM 16 GB (物理) + 6 GB (扩展)。
  v17 debug APK 已在此机器完成 1920×1080 × `{2,5,15,30}` × 5 次 AC-PERF 采集
  （2026-07-31，每档 ≥ 34× 余量 PASS —— 详见
  [`docs/probe-report.md`](probe-report.md) § 阶段 3 v17 debug 真机基准）。
- **signed Release 复采**：待 F3~F6 真机测试开闸后，在同一台 K80 Pro 上用 v18+ signed
  Release APK 复跑一次。
- **飞行模式验收设备**：同一台 K80 Pro（AC-016）。

### 冻结阈值

- **性能目标**（§10.2）：1920×1080 8 位 RGB，签名 Release APK，连续 5 次中位数
  - 2 轮 ≤ 6 s
  - 5 轮 ≤ 9 s
  - 15 轮 ≤ 27 s
  - 30 轮 ≤ 52 s
- **视觉质量阈值**（§12.3.3 三项自动指标）：见 [`docs/algorithm-v1.md`](algorithm-v1.md) §A.13。
- **资源上限**（§10.1）：MAX_INPUT_BYTES=50 MiB、MAX_EDGE=12288、MAX_PIXELS=50M、
  MAX_ASPECT_RATIO=64:1、MAX_SEGMENT_BYTES=1 MiB、MAX_PNG_TEXT_BYTES=64 KiB、
  MEMORY_FRACTION_LIMIT=60%。

---

## 2. AC 逐条追踪

### AC-001 —— 联合：签名 APK 可装可启动

- **要求**：签名 APK 可在 Android 8.0（API 26）+ arm64-v8a 设备正常安装、
  启动、进入首页；`targetSdk` 满足发布渠道要求。
- **自动**：Buildozer 构建冒烟（会走 [`scripts/wsl_build_android.sh`](../scripts/wsl_build_android.sh)
  产出 APK；构建失败即 fail）。
- **人工**：真机安装 + 启动 + 进首页确认。
- **证据**：v15 debug APK 已被用户装机确认（Stage 2b 收官）；v17 signed Release
  待 Stage 3 Block 3 出。
- **状态**：⏱ 待 Block 3 signed Release APK 出后由用户装机复测。

### AC-002 —— 人工：首页 / 打码 / 恢复 / 教程 / 提示 / 未保存退出

- **要求**：产品验收人逐项检查 FR-HOME 与流程要求。
- **人工**：用户走完打码 → 保存 → 分享 → 恢复 → 教程 → 未保存离开二次确认
  全流程。
- **证据**：v15 debug APK 用户已在 Stage 2b 走通主链路；
  未保存离开二次确认见 [`reversible_mosaic/ui/screens.py::ResultScreen._on_back`](../reversible_mosaic/ui/screens.py)。
- **状态**：⏱ v17 出后由用户回测 FR-HOME-003 首启一次性技术边界弹窗替代方案
  （MVP 用首页"教程与安全边界"入口，P1 补首启 dialog）。

### AC-003 —— 联合：格式支持 + 单图限制

- **自动**：[`tests/adversarial/test_malicious_inputs.py`](../tests/adversarial/test_malicious_inputs.py)
  Block 1 扩展 58 case 覆盖非法格式、超尺寸、异常元数据全部在算法前阻断。
- **人工**：用户在系统选择器选支持/不支持图片，确认 UI 提示清楚。
- **状态**：✅ 自动全绿；⏱ 人工待真机走查。

### AC-004 —— 自动：EXIF Orientation 1–8 修正

- **证据**：[`tests/unit/test_exif_orientation.py`](../tests/unit/test_exif_orientation.py)（Stage 1 存在）；
  8 组固定样本 transpose 后与预期一致，输出 PNG 不保留非 1 Orientation 字段。
- **状态**：✅ 自动全绿。

### AC-005 —— 自动：轮数 / 分享代码 / 前导零 / 随机码范围

- **证据**：
  - 轮数：[`tests/unit/test_algorithm_v1.py`](../tests/unit/test_algorithm_v1.py) +
    [`reversible_mosaic/core/algorithm/contracts.py::VALID_ROUNDS`](../reversible_mosaic/core/algorithm/contracts.py)。
  - 分享代码：[`tests/unit/test_share_code.py`](../tests/unit/test_share_code.py)（默认 500000、前导零、
    非数字、超大 seed、随机码 100000-999999 且避开默认值）。
- **状态**：✅ 自动全绿。

### AC-006 —— 自动：所有已发布算法版本零差异往返 + 固定向量不漂移

- **证据**：[`tests/vectors/test_v1_vectors.py`](../tests/vectors/test_v1_vectors.py)：
  断言 registry 当前后端（Cython 或参考）与冻结 `algorithm_v1.json` 逐字节一致。
  V1 已 FROZEN（2026-07-30），后续新增 V2 时会追加 vectors 文件。
- **状态**：✅ 自动全绿；Cython vs 参考实现比对在 Linux/WSL 里全绿，Windows
  正确 skip。

### AC-007 —— 人工：恢复页版本切换 + 元数据自动带入不锁定

- **证据**：[`reversible_mosaic/ui/screens.py::DecodeScreen`](../reversible_mosaic/ui/screens.py)
  始终显示算法版本 Spinner；元数据带入见 [`ui/input_hint.py::inspect_input`](../reversible_mosaic/ui/input_hint.py)
  返回 `suggested_algorithm_version` / `suggested_rounds`。
- **状态**：⏱ 待真机走查（Block 3）。

### AC-008 —— 自动：删除元数据后仍能逐像素恢复

- **证据**：[`tests/unit/test_pipeline.py`](../tests/unit/test_pipeline.py) 涵盖 encrypt→decrypt
  往返；[`tests/adversarial/test_malicious_inputs.py::test_write_png_serializes_metadata_that_parses_back`](../tests/adversarial/test_malicious_inputs.py)
  验证元数据往返；元数据删除后靠用户输入参数即可 —— 见 §12.2 item 7 需求。
- **状态**：✅ 自动全绿。**Block 1 新增**验证。

### AC-009 —— 人工：可选择参数执行恢复 + 可修改参数重试

- **证据**：[`ui/screens.py::ResultScreen`](../reversible_mosaic/ui/screens.py) 提供"返回修改参数"路径。
- **状态**：⏱ 待真机走查（Block 3）。

### AC-010 —— 自动：PNG 元数据 schema + 大小限制 + 异常处理 + encrypted/restored 区分

- **证据**：[`tests/unit/test_png_metadata.py`](../tests/unit/test_png_metadata.py) 基础用例；
  Block 1 扩展 20 case 覆盖 zTXt/iTXt 拒收、超 2048、非 ASCII、schema 未来版本、
  旧轮次（防误接受 pre-v14）、bool 代 int、5 candidates 过多、无 null 分隔符等。
- **状态**：✅ 自动全绿。**Block 1 扩展完成**。

### AC-011 —— 自动：分享代码不泄漏（PNG / 文件名 / 日志 / 历史 / 分享文字）

- **证据**：
  - PNG：[`reversible_mosaic/io/png_metadata.py::MosaicMetadata`](../reversible_mosaic/io/png_metadata.py) schema 里没有
    分享码字段。
  - 文件名：[`reversible_mosaic/domain/output_naming.py`](../reversible_mosaic/domain/output_naming.py) 只用原名 + `_mosaic` 后缀，
    与分享码解耦。
  - 分享文字：[`reversible_mosaic/android/native.py::AndroidOutputGateway.share`](../reversible_mosaic/android/native.py) 的 subject 是
    App 通用标识，覆盖测试见 [`tests/unit/test_android_native.py::test_share_subject_never_contains_share_code`](../tests/unit/test_android_native.py)。
- **状态**：✅ 自动全绿。**Block 1 加固**。

### AC-012 —— 联合：MediaStore 成功/失败/回滚 + 相册可见 + 分享 + 不覆盖输入

- **自动**：[`tests/unit/test_android_native.py`](../tests/unit/test_android_native.py) 14 case 覆盖 Android
  gateway 的 insert null / write IOError / SHA-256 mismatch / commit 失败四条
  路径的 pending 删除（FR-SAVE-006）。
- **人工**：v17 装机后走完 保存到相册 → 系统相册查看 → 系统分享。
- **状态**：⏱ 待 Block 3 真机验收。

### AC-013 —— 联合：并发/取消/状态恢复 + UI 可响应 + 不可重复启动 + 后台/失败重试

- **自动**：[`tests/unit/test_task_coordinator.py`](../tests/unit/test_task_coordinator.py) 12 case，Block 1
  扩展覆盖 cancel→reset→re-start、fail→reset→re-start、并发双 start 只一次
  通过、reset 在 mid-flight 状态被拒等。
- **人工**：真机点击取消按钮 + 切后台 + 重复点击开始按钮。
- **状态**：⏱ 待 Block 3 真机验收；自动 ✅。

### AC-014 —— 自动：资源边界 + 恶意样本 → 安全失败

- **证据**：[`tests/adversarial/test_malicious_inputs.py`](../tests/adversarial/test_malicious_inputs.py) 58 case
  + [`tests/unit/test_limits.py`](../tests/unit/test_limits.py)：所有异常输入必抛
  `ImageProbeError` 或 `MetadataStatus.INVALID`，绝不崩溃/无界内存/路径穿越/
  代码执行/半文件。Block 1 大幅扩展。
- **状态**：✅ 自动全绿。

### AC-015 —— 联合：质量指标 + 视觉���收

- **自动**：三项自动指标（像素变化率 / 相邻相关性 / 边缘相似度）在
  [`reversible_mosaic/core/algorithm/quality.py`](../reversible_mosaic/core/algorithm/quality.py) 实现；阈值冻结在
  [`docs/algorithm-v1.md`](algorithm-v1.md) §A.13；固定 20 图集在
  [`artifacts/visual_review/`](../artifacts/visual_review/) 每次跑 3 种子 × 4 轮数。
- **人工**：apeiria-network 单人 80 项打分（§12.3 单人 MVP 偏差路径）。
  签署单：[`artifacts/visual_review/scorecard.md`](../artifacts/visual_review/scorecard.md)。
  2 轮 20/20 / 5 轮 19/20 / 15 轮 16/20 / 30 轮 20/20 全部达标。
- **状态**：✅ MVP 首个内部发布路径通过；若面向公开用户发布须重新组织 ≥ 3
  名独立检查者按 §12.3 原条款复跑，该条款自动失效。

### AC-PERF —— 自动：性能与内存

- **自动**：真机基准直接由 App 内置自检屏 `Stage 3 AC-PERF 基准` 按钮跑
  1920×1080 × `{2, 5, 15, 30}` × 5 次 encrypt-only，median + P95 + 峰值 RSS
  自动落 App 私有目录 JSON（v17 遗留文件名 `stage0_perf.json`，v18+ 会用
  `stage3_bench.json`）。
- **v17 debug 真机数据**（2026-07-31 采集，小米 K80 Pro / Android 16 /
  RAM 16+6 GB；详见 [`docs/probe-report.md`](probe-report.md) § 阶段 3 v17
  debug 真机基准）：

  | rounds | median | P95 | peak_rss | 目标 | verdict |
  |---:|---:|---:|---:|---:|:---|
  |  2 | 0.103 s | 0.105 s | 269.3 MiB |  6 s | ✅ PASS (~58×) |
  |  5 | 0.256 s | 0.256 s | 269.6 MiB |  9 s | ✅ PASS (~35×) |
  | 15 | 0.767 s | 0.767 s | 270.0 MiB | 27 s | ✅ PASS (~35×) |
  | 30 | 1.533 s | 1.536 s | 270.5 MiB | 52 s | ✅ PASS (~34×) |

  实现 = `registry V1 backend = cython`；总扫描 12.9 s；每档以 ≥ 34× 余量通过。
- **状态**：✅ v17 debug 已在 1920×1080 × `{2,5,15,30}` × 5 次采集通过（新口径）；
  signed Release APK 复采待 C2 门槛开闸后真机装机时进行。debug vs Release
  性能差异一般 5–15%（Cython nogil 段几乎不受签名影响），预计复采仍以 ≥ 30×
  余量通过。

### AC-016 —— 联合：Manifest 权限 + 飞行模式

- **自动**：[`buildozer.spec`](../buildozer.spec) 的 `android.permissions` 仅声明
  `WRITE_EXTERNAL_STORAGE` (maxSdkVersion=28)，无 INTERNET / ACCESS_NETWORK_STATE 等。
- **人工**：真机开飞行模式跑完 选图 → 打码 → 保存 → 恢复 全流程。
- **状态**：⏱ 待 Block 3 真机验收。

### AC-017 —— 人工：交付物清点

- 见 [`docs/build-android.md`](build-android.md) § 6 交付物清单。
- **状态**：⏱ Block 3/4 收官后由用户对照清单勾。

---

## 3. 覆盖率总结

| 分类 | Case 数 | 全绿 | Skip | 备注 |
|---|---:|---:|---:|---|
| **unit** | ~170 | ✅ | 21（Windows 无 Cython） | 覆盖 share_code / task_state / limits / probe / normalize / png_metadata / exif / v1 algorithm / pipeline / task_coordinator / view_models / self_test_probes / optimized_v1 / quality / input_hint / output_naming / desktop_gateways / android_native |
| **property (hypothesis)** | 5 tests / ~170 examples | ✅ | 0 | V1 是双射 / 确定性 / Alpha 守恒 / 高轮数双射 / 非平凡输出 |
| **vectors** | 2 tests | ✅ | 0 | V1 冻结固定向量在参考与 registry 后端均对齐 |
| **adversarial** | 58 | ✅ | 0 | Block 1 扩展 PNG chunk / metadata schema / JPEG / write_png 四大类 fuzz |
| **合计** | **250 passed / 21 skipped** | | | Stage 3 Block 1 结束时数据 |

Stage 3 Block 2/3/4 的新增 case（Release APK 打包冒烟、性能基准、飞行模式
walk-through）落在真机人工/联合类，不进 pytest 主套件。

---

## 4. 未通过与已豁免

- **视觉验收 3 人复跑**：§12.3 单人 MVP 偏差豁免（`artifacts/visual_review/scorecard.md`
  首部记录）—— 仅 MVP 首次内部发布有效，公开发布必须重跑。
- **进程回收后恢复处理中任务**：FR-TASK-006 明规不承诺，无需验收。

---

## 5. 后续更新

Block 3 结束时本文档追加：

- v17 signed Release APK 的 AC-PERF 实测中位数 / P95 / 峰值 RSS 表格
- 飞行模式真机走查截图（用户回传）
- 系统分享接收方 App 列表快照（哪些能拉起分享 Intent）

Block 4 结束时本文档定稿为**测试报告**并入 `docs/release-notes.md` 的
"§ 5 版本历史 v0.1.0"作为交付物。
