# 测试计划与 AC 追踪（阶段 3）

> **版本**：0.1.0（阶段 3 测试报告，2026-08-03）
> **对应需求档**：[`requirements_product_v1.md`](../requirements_product_v1.md) §12–§14
> **状态标记**：✅ 通过 / ⏳ 进行中 / ⏱ 待人工 / ❌ 未通过 / — 不适用

本文档汇总 MVP 交付前所有验收条款的证据。每条 AC 都对应：
- **执行方**：自动 / 人工 / 联合（AC 表标注见需求档 §13）
- **证据位置**：具体测试文件、脚本输出或人工签署单
- **状态**：当前进度

已在 2026-08-03 完成 Block 4 文档核对；历史真机证据保留其原始采集
日期，未在本轮重新执行设备测试。

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

- **性能验收设备**：小米 K80 Pro / Android 16 / RAM 16 GB (物理) + 6 GB (扩展)。
  - **v17 debug** 已在此机器完成 1920×1080 × `{2,5,15,30}` × 5 次 AC-PERF 采集
    （2026-07-31，每档 ≥ 34× 余量 PASS）
  - **v18 signed Release** 已在此机器复采（2026-07-31，每档 ≥ 68× 余量 PASS，
    证书 SHA-256 `54c1bbbf...`，APK SHA-256 `c5ba1ba7...`）
  - 详见 [`docs/probe-report.md`](probe-report.md) § 阶段 3 v17 debug 与 v18 signed Release 真机基准。
- **飞行模式验收设备**：同一台 K80 Pro（AC-016 人工部分 2026-07-31 通过）。

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
- **证据**：**v18 signed Release APK 于 2026-07-31 在小米 K80 Pro / Android 16 手动装机
  启动 + 阶段 0 自检 + AC-PERF 基准全部完成**（详见 [`docs/probe-report.md`](probe-report.md)
  § 阶段 3 v18 signed Release 真机基准）。sdkVersion=26 / targetSdkVersion=34 /
  native-code=arm64-v8a（aapt dump 校验）。
- **状态**：✅ 通过。

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
- **人工证据**：v18 signed Release F4 走查（2026-07-31）确认 PNG + JPEG 主流程均正常。
- **状态**：✅ 自动全绿；✅ 人工 PNG + JPEG 通过（F4）。

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

- **证据**：[`tests/unit/test_pipeline.py::test_encrypt_then_restore_without_metadata_dependency`](../tests/unit/test_pipeline.py)
  明确去除 PNG 元数据后，以用户提供的算法版本、轮数和分享代码逐像素恢复；同一测试还
  断言加密输出文件名不含规范化分享代码。
- **状态**：✅ 自动全绿。

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
  - PNG 与文件名：[`tests/unit/test_pipeline.py::test_encrypt_then_restore_without_metadata_dependency`](../tests/unit/test_pipeline.py)
    断言规范化分享代码不出现在输出文件名；[`reversible_mosaic/io/png_metadata.py::MosaicMetadata`](../reversible_mosaic/io/png_metadata.py)
    schema 不含分享代码字段。
  - 分享边界：[`tests/unit/test_android_native.py::test_share_gateway_receives_fixed_subject_without_share_code`](../tests/unit/test_android_native.py)
    断言 gateway 只接收固定 subject；分享代码仅在用户明确触发复制时进入剪贴板。
  - 诊断边界：[`tests/unit/test_android_native.py::test_picker_failures_do_not_emit_or_persist_provider_details`](../tests/unit/test_android_native.py)
    与 `test_pipeline_failure_diagnostics_hide_input_and_share_code` 注入唯一 URI、路径和分享代码，
    断言 picker 不持久化 traceback，picker/pipeline 诊断不输出敏感值。
- **状态**：✅ 自动全绿。Block 4 已移除会泄漏 provider 异常详情的 picker/pipeline 诊断。

### AC-012 —— 联合：MediaStore 成功/失败/回滚 + 相册可见 + 分享 + 不覆盖输入

- **自动**：[`tests/unit/test_android_native.py`](../tests/unit/test_android_native.py) 14 case 覆盖 Android
  gateway 的 insert null / write IOError / SHA-256 mismatch / commit 失败四条
  路径的 pending 删除（FR-SAVE-006）。
- **人工**：v18 signed Release 装机后走完 保存到相册 → 系统相册查看 → 系统分享。
  **2026-07-31 F4 走查通过**：PNG + JPEG 打码后走保存到相册路径，系统相册（Pictures/ReversibleMosaic）
  可见输出文件；主链路无覆盖输入源。
- **状态**：✅ 通过（自动 + 人工均验收）。

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
- **状态**：✅ v17 debug 通过（1920×1080 × `{2,5,15,30}` × 5 次，K80 Pro，2026-07-31）；
  **v18 signed Release 复采于 2026-07-31 同机通过**（median 反而快 50%，归因于测试时
  手机充电锁高频 + 前置探针累计 RSS，不是代码差异；证书 fingerprint 与 v17 一致
  `54c1bbbf...`；APK SHA-256 `c5ba1ba7...`）：

  | rounds | median | P95 | peak_rss | 目标 | verdict |
  |---:|---:|---:|---:|---:|:---|
  |  2 | 0.051 s | 0.056 s | 484.8 MiB |  6 s | ✅ PASS (~118×) |
  |  5 | 0.127 s | 0.133 s | 484.8 MiB |  9 s | ✅ PASS (~71×) |
  | 15 | 0.341 s | 0.381 s | 484.8 MiB | 27 s | ✅ PASS (~79×) |
  | 30 | 0.762 s | 0.766 s | 484.8 MiB | 52 s | ✅ PASS (~68×) |

  实现 = `registry V1 backend = cython`；总扫描 8.6 s；每档以 ≥ 68× 余量通过。
- **v20 debug Cython 修复验证（2026-08-05）**：APK 静态检查已确认包内 `v1.so` 为 AArch64
  ELF，用户真机手动确认“V1 Cython 优化”探针符合预期。**AC-PERF 仍待用户手动运行并留存
  `stage3_bench.json`**；在该数据补齐前，v20 只构成 Cython 模块打包与加载修复证据，不新增
  性能验收结论。
- **v19 signed Release 限制（2026-08-05）**：冷缓存恢复构建虽通过签名与哈希复核，但真机
  Cython 探针显示模块缺失并回退 reference backend，故 **v19 不得作为 AC-PERF 或最终交付
  验收 APK**。须使用修复后的单入口脚本重建并核验 APK 内 `v1.so`、探针加载和 benchmark JSON
  的 `registry V1 backend = cython` 后，才可恢复该结论。

### AC-016 —— 联合：Manifest 权限 + 飞行模式

- **自动**：[`buildozer.spec`](../buildozer.spec) 的 `android.permissions` 仅声明
  `WRITE_EXTERNAL_STORAGE` (maxSdkVersion=28)，无 INTERNET / ACCESS_NETWORK_STATE 等。
  **v18 signed Release APK aapt dump 验证 2026-07-31 通过**：只见 `WRITE_EXTERNAL_STORAGE`
  与自动派生的 `READ_EXTERNAL_STORAGE`（两个都 `maxSdkVersion=28`），无 INTERNET /
  ACCESS_NETWORK_STATE / CAMERA / LOCATION / READ_MEDIA_*。sdkVersion=26 / targetSdkVersion=34 /
  native-code=arm64-v8a / package=`io.placeholder.reversiblemosaic`。
- **人工**：真机开飞行模式跑完 选图 → 打码 → 保存 → 恢复 全流程。
  **v18 signed Release 于 2026-07-31 在 K80 Pro / Android 16 上验收通过**（PNG + JPEG 两条解码路径、
  随机分享代码路径、encrypt + decrypt round-trip、MediaStore 保存到 Pictures/ReversibleMosaic
  且系统相册可见、深色 / 浅色 / 大字体三种系统设置下 UI 主链路均正常）。
- **状态**：✅ 通过。自动 Manifest + 人工飞行模式 + UI 兼容性主链路全部达标。

### AC-017 —— 人工：交付物清点

- **执行方**：产品验收人。按需求档 §16 与 [`docs/build-android.md`](build-android.md) §7
  逐项核验最终交付目录；本仓库的历史记录不替代实际 APK 与材料留存检查。
- **签署前清单**：
  - [ ] 源码、`pyproject.toml`、`requirements-dev.lock`、`buildozer.spec` 完整可读。
  - [ ] V1 算法规范、注册表与 `tests/vectors/algorithm_v1.json` 均在交付物中。
  - [ ] `tests/`、合成/视觉图集生成脚本、`docs/test-plan.md` 与 `docs/probe-report.md` 均在交付物中。
  - [ ] 三份 `artifacts/synthetic_test_set/*/manifest.csv` 与
    `artifacts/visual_review_sources/sources.csv` 可供核对来源、许可和 SHA-256。
  - [ ] 构建基线、`wsl_build_android.sh`、`docs/source-index.md` 可复现构建路径。
  - [ ] 最终签名 Release APK 已实际留存；SHA-256、`apksigner verify` 输出与
    `docs/release-notes.md` 的证书 fingerprint 一致。
  - [ ] `THIRD_PARTY_LICENSES/` 与 APK 内 `reversible_mosaic/assets/fonts/LICENSE.txt`
    都包含在交付物；教程、隐私边界与发行说明完整。
- **签署栏**：验收人：____________　验收日期：____________　APK 文件 SHA-256：____________
- **状态**：⏱ 待实际交付时由用户签署。当前不以历史文档代替 APK、许可证材料及交付目录的
  实际留存核验。

---

## 3. 覆盖率总结

| 分类 | Case 数 | 全绿 | Skip | 备注 |
|---|---:|---:|---:|---|
| **unit** | ~170 | ✅ | 21（Windows 无 Cython） | 覆盖 share_code / task_state / limits / probe / normalize / png_metadata / exif / v1 algorithm / pipeline / task_coordinator / view_models / self_test_probes / optimized_v1 / quality / input_hint / output_naming / desktop_gateways / android_native |
| **property (hypothesis)** | 5 tests / ~170 examples | ✅ | 0 | V1 是双射 / 确定性 / Alpha 守恒 / 高轮数双射 / 非平凡输出 |
| **vectors** | 2 tests | ✅ | 0 | V1 冻结固定向量在参考与 registry 后端均对齐 |
| **adversarial** | 58 | ✅ | 0 | Block 1 扩展 PNG chunk / metadata schema / JPEG / write_png 四大类 fuzz |
| **合计（Block 4）** | **253 passed / 21 skipped** | ✅ | 21（Windows 无 Cython） | 2026-08-03 完整 pytest；Block 4 新增隐私回归已纳入 |

Stage 3 Block 2/3/4 的新增 case（Release APK 打包冒烟、性能基准、飞行模式
walk-through）落在真机人工/联合类，不进 pytest 主套件。

---

## 4. 未通过与已豁免

- **视觉验收 3 人复跑**：§12.3 单人 MVP 偏差豁免（`artifacts/visual_review/scorecard.md`
  首部记录）—— 仅 MVP 首次内部发布有效，公开发布必须重跑。
- **进程回收后恢复处理中任务**：FR-TASK-006 明规不承诺，无需验收。

---

## 5. Block 4 收官记录（2026-08-03）

- 已修正 Android picker 与 pipeline 失败路径：诊断仅输出固定类别和异常类型，
  不再写入 traceback 或回显 provider URI、路径、原文件名及分享代码。
- 已新增行为级 AC-011 回归测试；本轮验证结果为 focused pytest **18 passed**、完整 pytest
  **253 passed / 21 skipped**。`ruff check .` 与 `mypy reversible_mosaic tests` 分别保留
  **9** 与 **23** 项历史基线诊断，Block 4 修改文件没有新增诊断。
- 保留 2026-07-31 的 v18 signed Release 真机、性能和 Manifest 证据；本轮不重复
  设备测试，也不把历史记录等同于当前交付物留存。
- AC-015 仍仅适用于内部 MVP 的单人偏差路径；公开或商业发布必须由至少三名独立
  检查者按 §12.3 重跑。
- AC-017 仍须由交付负责人核对实际 APK、许可证材料、交付目录和签署清单后完成。
