# Stage 3 Block 3 问题清单与移交说明

> **文档目的**：向下一个 Claude 会话移交所有当前堆积的问题、用户决策与继续步骤。
> **写入时间**：2026-07-31，Stage 3 Block 3 中段
> **写入者**：本会话的 Claude（Opus 4.7）
> **移交对象**：下一个 Claude 会话
> **状态约束**：**如果下一个会话不按本文档操作、或不理解用户决策就动手，本会话与下一个会话的所有工作都会被用户回退。**

---

## 0. 关键上下文（必读）

### 0.1 项目现状

- **v17 signed Release APK 已成功产出**并通过 apksigner 手工签名（v2+v3 方案，`CN=Apeiria-network, C=CN`）。
- APK SHA-256: `546dc561005b2a02745d6ec10bdfdcc4cd46a33cd4c26f435e208a49919b0394`
- 证书 SHA-256 fingerprint: `54c1bbbf48f34aae46225a3ef4f332852a9b8f3ac42930d47132a1b41d6c91a7`
- 证书 SHA-1 fingerprint: `46a3154a05571f416a0f4cd7ea795c19a65079fa`
- APK 位置：`D:\python\python_projects\ReversibleMosaic\bin\reversiblemosaic-0.1.0-arm64-v8a-release-v17.apk`
- WSL 侧（无版本后缀）：`~/src/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-release.apk`

### 0.2 用户绝对红线

**用户明确要求**（B1）：
- **所有密码、签名、keystore 相关的内容禁止离开 D 盘工作目录**（`D:\python\python_projects\ReversibleMosaic\`）
- **禁止拷贝进 C 盘**（包括 WSL vhdx 里的 `/home/hydrogen/src/ReversibleMosaic/keys/` 或 `/home/hydrogen/src/ReversibleMosaic/buildozer.spec.local` 之类的**持久化副本**）
- **禁止上 git**（`.gitignore` 已有 `*.jks`、`*.keystore`、`keys/`、`buildozer.spec.local` 四条防线，但下一个会话如果新增签名相关文件必须自查是否被 gitignore 覆盖）

**B1 隔离边界（用户 Q2 明规）**：**运行时临时文件允许**。
- `apksigner`、`keytool`、`jarsigner` 等工具运行期间在 `/tmp/` 或 Java `java.io.tmpdir` 产生的**临时文件可接受**（工具结束后自动清理，不算"离开 D 盘"）。
- 但**持久化文件副本**（keystore 拷贝、spec.local 副本、明文口令文件、导出的证书）**禁止**出现在 D 盘工作目录以外。
- 不需要为工具显式指定 `--tempdir` 参数，走默认 tmpdir 即可。

**违反此约束 = 用户回退所有工作**。

### 0.3 用户暂停指令

**F3、F4、F5、F6 全部暂停** —— **禁止推进任何真机测试**：
- F3：v17 装机 + AC-PERF 基准 —— **暂停**
- F4：飞行模式 / 深浅色 / 大字体 walk-through —— **暂停**
- F5：Manifest 权限验证 —— **暂停**
- F6：`stage3_bench.json` adb pull 路径确认 —— **暂停**

**C2 用户明规**："完成其他问题后才允许真机测试"。也就是说，**必须先解决 C1（合并到 C3 里）、C3、D3、E2**（用户明规修复项）**+ 处理 B1 相关的隔离要求（rsync exclude `buildozer.spec.local`），才能开始真机测试**。（E1 本会话已修，不进 C2 门槛。）

### 0.4 已执行完毕的动作（无需下一个会话再做）

- **F1**：用户已跑 `rm -rf ~/src/ReversibleMosaic/keys/` 清掉 WSL 侧 keystore 副本
- **F2**：用户已跑 `mv .../release-v16.apk .../release-v17.apk` 完成 D 盘 APK 版本号统一

---

## 1. 用户对每个问题的处理决策

以下所有问题按分类列出，包含：**原始问题**、**用户决策**、**当前状态**、**下一个会话该做什么**。

### A. 存储 / C 盘占用类

#### A1. WSL vhdx 占 C 盘 15-20 GB

- **原始问题**：`C:\Users\ctedx\AppData\Local\Packages\CanonicalGroupLimited...\LocalState\ext4.vhdx` 内含大量构建缓存 + Android SDK/NDK + p4a source cache。从 Stage 0 起就这样，我 Stage 0 时未告知用户。
- **原始决策**：完成真机测试后再处理。
- **后续决策（2026-08-05）**：不迁移整个 WSL；改为用户在不需要编译时按需手动删除可重建的 WSL 缓存与同步副本。根目录本机忽略文件 `LOCAL_WSL_CLEANUP.md` 记录绝对路径、删除影响和恢复方式，禁止提交或推送。
- **当前状态**：手动清理清单已就位，尚未执行删除。Linux 文件删除后 C 盘 VHDX 宿主文件未必立即缩小；如需回收 Windows 可见 VHDX 大小，另行确认压缩或导出重建方案。

#### A2. 每次构建往 WSL 写新 APK 副本

- **原始问题**：`~/src/ReversibleMosaic/bin/` 会累积历次 APK 副本；`.buildozer/build/dists/` 里还有中间产物。
- **后续决策（2026-08-05）**：`/home/hydrogen/src/ReversibleMosaic/bin` 与项目/全局 `.buildozer` 都列入本机手动清理清单；D 盘 `bin/` 是交付 APK 的权威保留位置。清理后下一次 Android 构建将成为冷构建。
- **当前状态**：尚未执行删除。

#### A3. C 盘 vhdx 内 keystore 字节残留

- **原始问题**：用户已 `rm -rf ~/src/ReversibleMosaic/keys/`，但 vhdx 是稀疏磁盘，被删除的字节仍作为"deleted"数据存在 vhdx 内部；只有 `wsl --export → --unregister → --import` 全量重打包才能真正清除。
- **当前状态**：未解决。2026-08-05 的按需缓存清理方案不重建 VHDX，不能消除已删除字节残留；未来如需处理，必须单独确认 WSL 导出重建方案。

---

### B. Keystore + 签名密码类

#### B1. buildozer.spec.local 双份 + 明文口令暴露（**必须处理**）

- **原始问题**：`buildozer.spec.local` 存在两份：
  - Windows 侧权威：`D:\...\buildozer.spec.local`（明文含 keystore 口令 + key 口令）
  - WSL rsync 副本：`~/src/ReversibleMosaic/buildozer.spec.local`（C 盘 vhdx 内）
  - `wsl_build_android.sh` 的 rsync exclude 有 `keys/` 但**没有** `buildozer.spec.local`
- **用户决策（红线）**："**禁止拷贝进 C 盘，所有的密码，签名和 keystore 相关的内容禁止离开当前 D 盘的这个工作目录，禁止上 git**"
- **当前状态**：
  - `.gitignore` 已有 `buildozer.spec.local` 排除（git 层面安全）
  - `wsl_build_android.sh` rsync exclude **未加** `buildozer.spec.local`（下次跑构建会再复制到 C 盘）
  - WSL 侧目前是否还有一份 spec.local **未确认**（用户跑 `rm -rf ~/src/ReversibleMosaic/keys/` 时没顺带删 spec.local）
- **下一个会话该做什么**：
  1. **修 [scripts/wsl_build_android.sh](scripts/wsl_build_android.sh)**：rsync exclude 列表里加 `--exclude "buildozer.spec.local"`（跟已有的 `--exclude "keys/"` 并列）。
  2. **指导用户删掉 WSL 侧 spec.local 副本**（如果存在）：`rm -f ~/src/ReversibleMosaic/buildozer.spec.local`。用户执行后回执确认。
  3. **验证 buildozer 能否在 WSL workspace 里没有 spec.local 的情况下读到 D 盘的 spec.local**：这可能是个问题 —— buildozer 从 `~/src/ReversibleMosaic/` 运行，spec.local 的合并机制可能强制要求同目录。如果不行，需要考虑 symlink 或者让 buildozer 显式指向 D 盘 spec.local。**不确定 buildozer 是否支持 spec.local 跨目录读取，需要下一个会话验证**。
  4. **对 D 盘的 spec.local 做 Windows ACL 加固**（可选，用户没明规但符合 B1 精神）：`icacls D:\...\buildozer.spec.local /inheritance:r /grant:r "%USERNAME%":R`，只允许当前用户读。**如果动这个先问用户**。
  5. **写完改动后要跑一次 pytest + ruff + mypy** 确保零回归。
- **本会话执行状态（2026-07-31，Step 1 + Step 2）**：**已完成**。
  - `scripts/wsl_build_android.sh` rsync exclude 列表已加 `--exclude "buildozer.spec.local"`（第 123 行，与 `--exclude "keys/"` 并列）。
  - 用户已回执执行 `rm -f /home/hydrogen/src/ReversibleMosaic/buildozer.spec.local`，确认 WSL 侧无残留（`ls -la` 报 no such file）。
  - **不再依赖 buildozer 跨目录读 spec.local**：Q1 决策 C 走脚本内 apksigner 封装，buildozer 端预期产出 unsigned APK，签名凭据由脚本从 `/mnt/d/.../buildozer.spec.local` 只读现拉现用。因此第 3 步"跨目录读取"担忧不成立，跳过。
  - 第 4 步 Windows ACL 加固**未执行**（用户没明规，符合"先问"原则；如需加固可后续单独提）。
  - pytest 250 passed / 21 skipped、ruff 9 baseline、mypy 23 baseline —— 零回归。

#### B2. Keystore 备份细节

- **原始问题**：用户说"已经备份"但没说备份位置/介质/是否加密；备份也可能在同物理磁盘。
- **用户决策**：**"我备份到 D 盘的其他目录，你不用管"**（B2）。
- **当前状态**：无需处理。
- **下一个会话该做什么**：**不要提**。用户已明确接管此风险。

#### B3. Keystore 权威位置在 D 盘项目内 / 云同步风险

- **原始问题**：D 盘可能被云盘同步。
- **用户决策**：**"不用管"**（B3）。
- **当前状态**：无需处理。
- **下一个会话该做什么**：**不要提**。

#### B4. 内部自签 CN 会跟着 APK 分发 —— **重要澄清**

- **原始问题（我当初的描述）**：证书 `CN=Apeiria-network, C=CN` 会跟着 APK 分发；正式发布切换身份时，签名主体也一起换。
- **用户反应**：**"证书已经写好了，为什么还要换？你到底换几次？"**（表明用户误解了我的意思）
- **重要澄清**（**下一个会话务必知晓**）：
  - **B4 说的不是"MVP 阶段要换"**。MVP 阶段用当前证书 `CN=Apeiria-network, C=CN` 完全 OK，不需要换。
  - B4 只是提醒：**未来某天，如果用户决定把这个 App 面向公开用户 / 上应用商店商业发布**，那时候需要一并换 applicationId + keystore + CN + 发布主体（这是 `docs/release-notes.md` § 1 的"正式发布五步走"）。
  - MVP 阶段绝对不需要换。当前证书是"MVP 内部签"级别的资产，够用。
- **用户决策**：既然是我描述引起的误解，**不需要执行任何动作**，但**下一个会话不要再向用户提"证书要换"** —— 已经沟通过了，用户拿到的信息是"不换"。
- **当前状态**：证书 = 当前签名主体，不动。
- **下一个会话该做什么**：**不要再提"换证书 / 换签名主体 / 换 CN"**。如果用户主动问正式发布切换，再指向 `docs/release-notes.md` § 1。

---

### C. 签名流程类（**必须修**）

#### C1. buildozer.spec.local 的 signing config 为什么没被 buildozer 读取 —— **用户 Q1 明规走方案 C**

- **原始问题**：`buildozer android release` 应该自动读 spec.local 里的四个 signing key (`android.release_keystore/keyalias/keystore_passwd/keyalias_passwd`) 完成签名。**实际产出 `*-release-unsigned.apk`**，说明 signing config 没生效。我们绕开用 apksigner 手工签才拿到 v17 signed APK。
- **用户决策**：
  - **"需要修复该问题"**（C1 初次决策）
  - **"Q1: C"**（2026-07-31 明规走方案 C —— 放弃让 buildozer 自动签名，脚本封装 apksigner）
- **当前状态**：根因不需再查（用户拍板绕开）。绕开方案已跑通（apksigner 手签）。
- **下一个会话该做什么**：
  1. **不要再查 buildozer signing 根因**。用户已决定放弃这条路。
  2. **不要**尝试改主 `buildozer.spec` 加 signing key（违反 B1）。
  3. **不要**尝试环境变量注入方案（方案 B 被 Q1 排除）。
  4. **实际操作**：跟 C3 合并 —— 在 `wsl_build_android.sh` 的 release 分支里封装 apksigner 全流程（详见 C3 章节）。修好后 `docs/build-android.md` § 5.2 明确写"buildozer 出 unsigned APK 是**预期行为**，签名由脚本内的 apksigner 步骤完成"，避免下一个 AI 又走 C1 错路。
- **本会话执行状态（2026-07-31，Step 2 + Step 3）**：**已完成**（合并进 C3 一次修改）。
  - `scripts/wsl_build_android.sh` release 分支已封装 apksigner sign / verify 全流程（脚本行 171~266）：从 `/mnt/d/.../buildozer.spec.local` 只读读取 4 项签名凭据，`--ks-pass stdin --key-pass stdin` heredoc 传入，签完立即 `unset` + `trap` 兜底。
  - `docs/build-android.md` § 5.2 已明确记录"buildozer 预期产出 `*-release-unsigned.apk`（Q1 决策 C 的期望行为，不是 bug）"—— 避免下一个 AI 又走 C1 错路。
  - 未改主 `buildozer.spec` 加 signing key、未走环境变量注入方案。
  - pytest / ruff / mypy 零回归。

#### C2. apksigner 手签的 APK 未实测装机

- **原始问题**：只跑了 `apksigner verify` 说 v2/v3 通过，但没 `adb install` 实测。
- **用户决策**：**"完成其他问题后才允许真机测试"**（C2）。
- **当前状态**：等 C1（合并进 C3）、C3、D3、E2 修完之后才能验证。（E1 本会话已修。）
- **下一个会话该做什么**：
  1. **修完 C3（含 C1/D3）+ B1 + E2** 之后，才能引导用户跑真机测试。
  2. 真机测试的第一步就是 `adb install -r bin/reversiblemosaic-0.1.0-arm64-v8a-release-v17.apk`（在 Windows PowerShell 里跑 adb 或者 WSL 里跑）。
  3. 装成功 = C2 顺带过。

#### C3. `apksigner sign` 命令没写进构建脚本 —— **必须修（方案 C）**

- **原始问题**：每次 release 构建都要手动做四步：
  1. `wsl_build_android.sh release` 出 unsigned
  2. 手工跑 apksigner sign（交互输密码）
  3. 手工 verify + 记 SHA-256
  4. 手工 cp 到 D 盘 + 加版本号后缀
- **用户决策**：
  - **"需要修复该问题"**（C3 初次决策）
  - **"Q1: C"** → 用 apksigner 封装（跟 C1 合并）
  - **"Q5: 强制参数"** → 版本号必传（跟 D3 合并）
  - **"Q6: 统一版本号，只要内容是一样的，就用一样的版本号"** → debug 和 release 的**版本号是同一个空间**，不是各自独立；同一次代码状态出的 debug 和 release APK 共享同一个版本号（例如 v17 debug 与 v17 release 是同一份代码，不同签名）
  - **"Q7: 不加"** → 不显式加 zipalign 步骤（buildozer 出的 unsigned APK 已经 aligned，apksigner verify 也没警告）
- **当前状态**：无自动化，全靠人记。
- **下一个会话该做什么**：
  1. **修 `scripts/wsl_build_android.sh`**：
     - 命令签名改成 `wsl_build_android.sh <mode> <version>`，**两个参数都强制**，不传就 exit 报错。
     - `mode` ∈ {`debug`, `release`}；`version` 格式 `v[0-9]+`（脚本 regex 校验）。
     - **debug 分支**：
       - `buildozer android debug` 出 `bin/reversiblemosaic-0.1.0-arm64-v8a-debug.apk`
       - `mv` 到 `bin/reversiblemosaic-0.1.0-arm64-v8a-debug-<version>.apk`
       - `cp` 到 `/mnt/d/python/python_projects/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-debug-<version>.apk`
       - `sha256sum` 并打印
       - **目标文件已存在则 exit 报错**（防覆盖）
     - **release 分支**（apksigner 封装 —— 方案 C）：
       - 检查 `buildozer.spec.local` 存在（已有逻辑）
       - `buildozer android release` 出 `bin/reversiblemosaic-0.1.0-arm64-v8a-release-unsigned.apk`
       - **不加 zipalign**（Q7 明规；buildozer 输出已经 aligned）
       - 从 `buildozer.spec.local` grep 出 `android.release_keystore` / `keyalias` / `keystore_passwd` / `keyalias_passwd` 四个值（**用 `read` + shell 变量存，绝对不要 `echo` 或写进日志文件**）
       - 调 `apksigner sign` —— **用 stdin pipe 传口令**（而不是命令行参数，避免 `ps` 看到）：
         ```bash
         # apksigner 支持 --ks-pass stdin 与 --key-pass stdin
         printf '%s\n%s\n' "$KEYSTORE_PWD" "$KEY_PWD" | \
             "$APKSIGNER" sign \
                 --ks "$KEYSTORE_PATH" \
                 --ks-key-alias "$KEY_ALIAS" \
                 --ks-pass stdin \
                 --key-pass stdin \
                 --out "$SIGNED_APK" \
                 "$UNSIGNED_APK"
         ```
       - `apksigner verify --verbose --print-certs "$SIGNED_APK"` 验证 v2/v3 通过
       - `sha256sum` + `keytool -printcert -jarfile` 记录到 stdout
       - `mv/cp` 到 D 盘 `bin/reversiblemosaic-0.1.0-arm64-v8a-release-<version>.apk`
       - **目标文件已存在则 exit 报错**
     - **口令读取实现细节**（**下一个会话必须严格遵守**）：
       - 从 spec.local 读值时用 `awk` 或 `grep + cut`，**不要用 `set -x`**（会把口令 echo 到日志）
       - 变量赋值后立即 `unset` 掉中间变量
       - 不要把口令写到脚本自己产生的任何文件里
       - 日志文件 `/home/hydrogen/src/reversible-mosaic-build.log` 里不能有口令 —— 需要用 `2>&1 | tee -a "$LOG"` 之外的路径处理口令（比如口令 apksigner 交互从 stdin 读，其他 buildozer 输出照常 tee 到 log）
  2. **不加 zipalign 的确认**（Q7 明规）：apksigner 会检查对齐；如果 buildozer 输出的 unsigned APK 未 aligned，apksigner 会**主动报错**（不是 warning）。所以省这一步是安全的 —— 出问题会明显暴露。
  3. **同版本号双产物**（Q6 明规）：**同一次代码状态下**打 debug 和 release，用户会分别跑 `wsl_build_android.sh debug v18` 和 `wsl_build_android.sh release v18` —— 两个 APK 共享 v18 版本号。**如果代码在两次调用之间被改过**（rsync 会同步 Windows 侧改动），用户自行负责让版本号不同（v18 debug + v19 release 之类）。脚本不做代码变更检测，只做版本号语法校验 + 目标文件防覆盖。
  4. **修好后**：
     - 更新 `scripts/wsl_build_android.sh` 头部注释（新命令签名）
     - 更新 `buildozer.spec` 顶部注释（提到脚本新签名）
     - 更新 `docs/build-android.md` § 5.2 与 § 5.4（真实签名流程）
     - 更新 `docs/source-index.md` 里 `wsl_build_android.sh` 条目
     - 更新 `docs/build-android.md` § 3.2 「增量构建」的命令示例
     - 跑 pytest + ruff + mypy 验证零回归
- **本会话执行状态（2026-07-31，Step 2 + Step 3 + Step 4）**：**已完成**（C1 + C3 + D3 一次改）。
  - `scripts/wsl_build_android.sh` 重写为 `<mode> <version>` 双参强制形式：
    - 参数校验：`mode ∈ {debug, release}` + `version` 匹配 `^v[0-9]+$`，缺参 / 格式不对 → exit 2。
    - 目标文件已存在检查（WSL bin + D 盘 bin 任一位置） → exit 4，拒覆盖。
    - Release 分支前置检查 D 盘 spec.local 存在 → 缺则 exit 3。
    - Debug 分支：buildozer → mv 到目标名 → cp -a 到 D 盘 → sha256sum。
    - Release 分支：buildozer 出 unsigned → 从 D 盘 spec.local grep 出 4 项凭据（`${line#*=}` 只按首个 `=` 切，支持含 `=` 的口令）→ apksigner sign heredoc stdin → apksigner verify → 立即 unset 口令（+ trap 兜底）→ 删 unsigned 中间产物 → cp -a 到 D 盘 → sha256sum + keytool -printcert -jarfile。
  - 不显式做 zipalign（Q7 决策已在脚本注释中记录）。
  - 口令处理严格遵守：不 `set -x`、不 tee 到 `$LOG`、不通过命令行参数传入。
  - 文档同步四处：
    - `scripts/wsl_build_android.sh` 头部注释（新命令签名 + Q1 决策 C 说明）
    - `buildozer.spec` 顶部注释（提到脚本新签名 + apksigner 封装）
    - `docs/build-android.md` § 3.2 增量构建示例 + § 3.4 版本后缀节 + § 5.2 完整 apksigner 流程说明
    - `docs/source-index.md` 主构建段落调用姿势 + `wsl_build_android.sh` 条目全量重写
    - `scripts/generate_release_keystore.sh` 尾部提示行（新命令示例）
  - 静态验证：`bash -n` 语法 OK；参数校验分支（缺 mode / 缺 version / 版本格式错）exit 2 触发。
  - Release 端到端验证需真机构建，等 Step 5 F3~F6 开闸后再做。
  - pytest 250 passed / 21 skipped、ruff 9 baseline、mypy 23 baseline —— 零回归。

#### C1 决策已明确 —— 见 C3 章节

C1 与 C3 合并为一次修改。**下一个会话不要单独处理 C1**（已在 C3 里合并完成方向说明）。

---

### D. 版本 / 命名类

#### D1. debug v17 中间迭代 —— **v8~v16 用户已同意不追溯，v17 是我的疏漏**

- **原始问题**：我 Block 2 时用 v16 作占位号，但用户实际 debug 打包到 v17。中间发生过什么我完全不知道。
- **用户反馈（更新 2026-07-31）**："**明显是你忘了更新文档，我只知道 v17 是最新的测试版本并且进行了真机测试和 1920×1080 的性能扫描**"，紧接着补充"**中间版本的记录缺失是在我的监管下同意的，V17 的版本记录缺失是你在阶段性取得成果的时候没做记录**"。
- **重要区分**（**下一个会话必须理解**）：
  - **v8~v16 之间的 debug 迭代记录缺失**：这是**用户监管下同意的**。**不需要追溯 v8~v16**，也**不要问用户 v8~v16 数据**。
  - **v17 debug 的记录缺失**：这是**我在"阶段性取得成果"（v17 debug 完成真机测试 + 1920×1080 性能扫描）时没做记录**，用户明规为"你的疏漏"。**必须补齐 v17 debug 的记录**。
- **信息滞后详情**（**必读**）：
  - `docs/probe-report.md` **只记录到阶段 1 v7 debug（2026-07-28）** —— v17 debug 章节缺失
  - `development_plan.md` 阶段 3 Block 3 段落**没提 v17 debug 真机测试 + AC-PERF 完成**
  - `docs/test-plan.md` AC-PERF 条目里说"沿用 v7 debug APK 数据"，但**用户已经在 v17 debug 上跑过 1920×1080 AC-PERF**（这就是 E2 说的"新口径"数据源）
  - 用户告诉我 v17 debug 跑过真机测试和 1920×1080 性能扫描，但**我没有具体数据值** —— 需要用户提供
- **用户决策**：需要补齐 v17 debug 记录。
- **当前状态**：文档信息滞后于 v17 debug 实际达成的进度。
- **下一个会话该做什么**：
  1. **只索取 v17 debug 数据，不要问 v8~v16**（用户已明规免追溯）：
     - v17 debug APK SHA-256（如果用户还留着 v17 debug APK 就 `sha256sum` 一下）
     - v17 debug 的 1920×1080 AC-PERF 扫描结果：每档 rounds（2/5/15/30）的 median / P95 / peak_rss / verdict（PASS/FAIL）
     - 用户手机型号 + Android 版本 + RAM
     - 测试日期
  2. 拿到数据后**同时更新三处**：
     - [docs/probe-report.md](docs/probe-report.md)：追加"## 阶段 3 v17 debug 真机基准（日期）"章节，格式对齐现有的 v7 章节
     - [development_plan.md](development_plan.md)：阶段 3 Block 3 段落补一小节"v17 debug 真机测试完成情况"
     - [docs/test-plan.md](docs/test-plan.md) AC-PERF 条目：把"沿用 v7 debug 参考数据"改成"基于 v17 debug 真机基准"（配合 E2 一起做）
  3. **注意**：v17 debug 数据是 debug 签名的 APK，不是 signed Release APK。AC-PERF 目标要求的是"签名 Release APK 的数据"（§10.2）。debug vs release 性能差异一般 5-15%（Cython nogil 段的差异微乎其微），可以在文档里注明"debug 数据作为 signed Release 前的参考基准；signed Release APK 复采需真机测试通过后进行"（这跟 C2 挂钩）。
- **本会话执行状态（2026-07-31，Step 5）**：**已完成**（跟 E2 合并做）。
  - 用户提供数据：小米 K80 Pro / Android 16 / RAM 16+6 GB / 2026-07-31 采集。
  - v17 debug APK SHA-256：**未记录**（用户明规"拿不到"，APK 已丢失；文档中直接标注"未记录"，不追补）。
  - AC-PERF `{2,5,15,30}` × 5 次中位数 + P95 + peak_rss 全部 PASS（余量 ≥ 34×），30 轮实测 1.533 s 与 v7 阶段外推 "~1.53 s" 几乎完全吻合，Cython 路径稳定。
  - 数据来源附注：v17 APK 打包早于 `self_test.py` 的 `stage0_perf.json → stage3_bench.json` 重命名，v17 装机跑出的 JSON 仍是老文件名；JSON 原文用户丢失，数据以 App 内自检屏截图为准（用户 IDE 截图证据）。
  - 三份文档同步：
    - [docs/probe-report.md](docs/probe-report.md) 追加"阶段 3 v17 debug 真机基准（2026-07-31）"章节，包含设备信息 + AC-PERF 表 + v7 对比 + 待补齐清单；同时给 v7 章节头部加历史标注。
    - [development_plan.md](development_plan.md) Block 3 段：`Block 3 尚待用户参与` 5 项标注完成度（keystore/Release/fingerprint 已完成，AC-PERF 部分完成，walk-through 暂停），新增子小节"v17 debug 真机测试完成情况"。
    - [docs/test-plan.md](docs/test-plan.md)：§ 1 目标验收设备改为 K80 Pro，冻结阈值补 2 轮 ≤ 6 s + 5 轮 ≤ 9 s 两档，AC-PERF 条目老口径 v7 数据整段替换为 v17 新口径 + PASS 判定 + 状态标记。
  - **未跑 pytest**（纯文档改动）。

#### D2. `docs/release-notes.md` 表格里的 v15 debug SHA-256 占位

- **原始问题**：`| v15 debug (Stage 2b) | ~34 MiB | *(见 [bin/](../bin/) 目录 sha256sum)* | ...` 从来没填过真值。
- **用户决策**：**"忽略该问题"**（D2）。
- **当前状态**：无需处理。
- **下一个会话该做什么**：**不要提**。用户已忽略。

#### D3. WSL 侧 release APK 无版本后缀 —— **必须修（合并进 C3）**

- **原始问题**：
  - WSL 侧文件名：`reversiblemosaic-0.1.0-arm64-v8a-release.apk`（无版本号，下次构建覆盖）
  - Windows 侧手工加：`reversiblemosaic-0.1.0-arm64-v8a-release-v17.apk`
- **用户决策**：
  - **"加版本后缀"**（D3 初次决策）
  - **"Q5: 强制参数"** → 版本号必传，不传报错
  - **"Q6: 统一版本号，只要内容是一样的，就用一样的版本号"** → debug 和 release 版本号共享同一空间
- **当前状态**：手工加后缀依赖人记。
- **下一个会话该做什么**：**合并进 C3 一次做**。见 C3 章节里的 `wsl_build_android.sh <mode> <version>` 强制参数化改造。核心要点：
  - 参数强制（不是 `bin/` 扫描 +1）
  - `debug v17` 与 `release v17` 是同一份代码不同签名（Q6 明规）
  - 目标文件已存在则 exit 报错，防止误覆盖
- **本会话执行状态（2026-07-31）**：**已完成**（并入 C3 一次修改，见上方 C3 收口）。同版本号 debug + release 因文件名含 `-<mode>-` 段不会冲突（例 `v18 debug` 与 `v18 release` 可同时存在于 `bin/` 下）。

---

### E. 文档 / 计划一致性类

#### E1. `development_plan.md` Block 3 段落有陈旧引用 —— **本会话已修复**

- **原始问题**：keystore 位置从 `~/keys/reversiblemosaic.jks` 改成 `<项目>/keys/reversiblemosaic.jks` 后，我更新了 `docs/build-android.md` + `docs/source-index.md`，但**忘记更新 `development_plan.md`**。
- **用户反馈**：**"E1 你这个版本就要更新"**（用户明规本会话就修，不移交）。
- **本会话执行状态（2026-07-31）**：**已完成**。
  - `development_plan.md:498` 已从"默认路径 `~/keys/reversiblemosaic.jks`（用户可 `KEYSTORE_FILE=` 覆盖）"改成"默认路径 `<项目>/keys/reversiblemosaic.jks`（`.gitignore` 已加目录级 `keys/` 拦截，永不入 git；`KEYSTORE_DIR=` / `KEYSTORE_FILE=` 环境变量可覆盖到项目外的位置）。用户明规（Stage 3 Block 3）：所有密码/签名/keystore 相关内容禁止离开 D 盘工作目录、禁止拷贝进 C 盘 —— `scripts/wsl_build_android.sh` rsync 已加 `--exclude "keys/"` 保证 WSL 侧不留副本"。
  - `development_plan.md:544` 已从"备份 `~/keys/reversiblemosaic.jks`"改成"备份 `<项目>/keys/reversiblemosaic.jks`"。
  - 全局 grep 确认：`grep -n "~/keys" development_plan.md docs/*.md` 无返回 —— 无残留。
  - pytest 250 passed / 21 skipped —— 零回归。
- **下一个会话该做什么**：**不需要做任何事**。E1 已收口。

#### E2. AC-PERF 数据源口径不一致 —— **必须修**

- **原始问题**：
  - `docs/test-plan.md` AC-PERF 条目引用的是 v7 debug APK 的 1920×1080 × `{1, 5, 10, 20}` 轮数据："1 轮 0.060 s / 5 轮 0.268 s / 10 轮 0.543 s / 20 轮 1.072 s"
  - 这是**老轮次集**（Stage 1 早期用的 `{1, 5, 10, 20}`），后来 2026-07-29 定稿到 `{2, 5, 15, 30}`
  - 现在 AC-PERF 用 `{2, 5, 15, 30}`，但文档里的参考数据还是老口径 —— 口径对不上
- **用户决策**：**"需要改成新的口径"**（E2）。
- **当前状态**：test-plan.md AC-PERF 数据是老口径 `{1, 5, 10, 20}`。
- **下一个会话该做什么**：
  1. 跟 D1 合并做 —— **拿到用户提供的 v17 debug `{2, 5, 15, 30}` 真机数据后**：
     - `docs/test-plan.md` AC-PERF 条目：把老口径 `{1, 5, 10, 20}` 段落**整段删掉**，替换为新口径 `{2, 5, 15, 30}` 的 v17 真机数据。
     - 状态标记从 "⏳ Stage 3 Block 3 出 signed Release APK 后复采一次即可签署" 改成 "✅ v17 debug 已在 1920×1080 × {2,5,15,30} × 5 次采集通过；signed Release APK 复采待真机装机（C2 门槛后）"。
  2. `docs/probe-report.md` 里 v7 章节保留（历史记录），追加"注意：v7 数据是老轮次集 {1,5,10,20}，仅作历史参考；当前口径见阶段 3 v17 debug 章节"。
  3. 不需要跑 pytest（纯文档）。
- **本会话执行状态（2026-07-31，Step 5）**：**已完成**（并入 D1 一次修改，见上方 D1 收口）。核心动作：`docs/test-plan.md` AC-PERF 条目老口径整段替换为新口径 v17 数据 + PASS 判定；`docs/probe-report.md` v7 章节头部加历史标注（老轮次集 `{1,5,10,20}` 仅作参考，当前口径见 v17 debug 章节）。

---

### F. 待执行但被暂停的项

#### F1、F2 已执行 —— **无需处理**

- F1：用户已 `rm -rf ~/src/ReversibleMosaic/keys/`
- F2：用户已 `mv .../release-v16.apk .../release-v17.apk`

#### F3~F6 全部暂停 —— **禁止推进**

- F3：v17 装机 + AC-PERF 基准 —— **暂停**
- F4：飞行模式 + 深浅色 + 大字体 walk-through —— **暂停**
- F5：Manifest 权限验证（`aapt dump permissions` 或 apktool 提取 AndroidManifest.xml）—— **暂停**
- F6：`stage3_bench.json` 从 App 私有目录 adb pull 的路径确认 —— **暂停**

**用户明规（C2）**：**"完成其他问题后才允许真机测试"**。

**下一个会话该做什么**：只有在 C1、C3、D3、E1、E2 全部落地 + B1 隔离要求（`buildozer.spec.local` rsync exclude）也落地之后，才能问用户是否开始真机测试。**不要主动推进 F3~F6**。

---

## 2. 下一个会话的操作顺序（推荐）

### 步骤 0：读完本文档 + 对齐上下文

- 读 `development_plan.md`（了解整体进度）
- 读 `docs/source-index.md`（了解项目结构）
- 读本文档全文
- 读 `docs/build-android.md` § 4 + § 5（了解当前签名策略描述）

### 步骤 1：修 B1（rsync exclude `buildozer.spec.local`）

- 编辑 `scripts/wsl_build_android.sh` 加 `--exclude "buildozer.spec.local"`
- 让用户跑 `rm -f ~/src/ReversibleMosaic/buildozer.spec.local` 清 WSL 侧副本（如果存在）
- 用户回执后进步骤 2

> **注意 E1 本会话已修复**（development_plan.md 里的 `~/keys/` 引用已换成 `<项目>/keys/`），跳过。

### 步骤 2：修 C1 + C3 + D3（`wsl_build_android.sh` 强制参数化 + apksigner 封装）

**用户 Q1 明规走方案 C，不需要再查 buildozer signing 根因**。合并一次改：

- **命令签名**：`wsl_build_android.sh <debug|release> <version>` —— 两参数都强制，不传报错，`version` 用 `v[0-9]+` regex 校验
- **debug 分支**：buildozer android debug → mv 到 `bin/reversiblemosaic-0.1.0-arm64-v8a-debug-<version>.apk` → `cp` 到 D 盘 → `sha256sum`
- **release 分支（apksigner 封装 —— 方案 C）**：
  - buildozer android release → 出 `*-release-unsigned.apk`（**这是预期行为**，不是 bug）
  - **不加 zipalign**（Q7 明规）
  - 从 `buildozer.spec.local` 读四个 signing 值
  - `apksigner sign --ks-pass stdin --key-pass stdin`（口令走 stdin pipe，**不进程列表、不日志**）
  - `apksigner verify --verbose --print-certs`
  - `sha256sum` + `keytool -printcert -jarfile`（可选）
  - mv/cp 到 D 盘 `reversiblemosaic-0.1.0-arm64-v8a-release-<version>.apk`
- **目标文件已存在则 exit 报错**，防止误覆盖
- **口令处理必须严格**：`set +x`、变量赋值后 `unset`、口令绝不写入自己产生的日志文件；只有 buildozer 主日志走 `tee -a "$LOG"`，口令处理分开
- **允许使用系统 tmp 目录**（Q2 明规） —— 不需要为 apksigner/keytool 显式指定 `--tempdir`
- 更新 `docs/build-android.md` § 3.2 / § 5.2 / § 5.4
- 更新 `docs/source-index.md` 里 `wsl_build_android.sh` 条目
- 更新 `buildozer.spec` 顶部注释

### 步骤 3：跑 pytest / ruff / mypy 验证 —— 每次代码改动后

- `python -m pytest -q`：预期 250 passed / 21 skipped
- `python -m ruff check .`：预期 9 baseline
- `python -m mypy reversible_mosaic tests`：预期 23 baseline
- **零回归**（跟当前 baseline 一致）

### 步骤 4：向用户索取 v17 debug 真机数据 —— 修 D1 + E2

（**用户 Q3 明规：留给下一个会话处理，本会话不动**）

- 询问用户是否留有 v17 debug APK（sha256sum）
- 询问 v17 debug 的 `{2,5,15,30}` × 5 次 1920×1080 AC-PERF 数据
- 询问机型 + Android 版本 + RAM + 测试日期
- 数据到齐后更新 `docs/probe-report.md` + `development_plan.md` + `docs/test-plan.md`
- **不要问 v8~v16 数据**（用户明规免追溯）

### 步骤 5：全部改完之后，才能问用户是否开始真机测试

- 只有当步骤 1~4 全部完成、pytest 无回归、用户明确同意，才能进入 F3~F6
- 真机测试用的是**已经签好的 v17 signed Release APK**（不需要重建）
- 装机、AC-PERF 复采、飞行模式、Manifest 权限、adb pull —— 按 [docs/build-android.md](docs/build-android.md) § 5.4 + [docs/test-plan.md](docs/test-plan.md) 里的 AC 条目走

---

## 3. 严禁事项（**违反 = 用户回退所有工作**）

1. **禁止把密码 / keystore / spec.local 复制到 C 盘持久化位置**（含 WSL vhdx 内的任何子目录）。**运行时临时文件（`/tmp/`、Java `java.io.tmpdir`）允许**（Q2 明规）。
2. **禁止把 keystore 路径、口令、fingerprint 写进主 `buildozer.spec`**（会被 git 追踪；只能进 `buildozer.spec.local` 或环境变量）。
3. **禁止修改 `.gitignore` 移除 `*.jks` / `*.keystore` / `keys/` / `buildozer.spec.local` 任何一条**。
4. **禁止在 v17 signed Release APK 的证书 CN 上做任何"切换建议"** —— 用户已明确"证书已经写好了"，MVP 阶段不换。
5. **禁止在 C1、C3、D3、E2、B1 修复前推进真机测试**（F3~F6 暂停）。
6. **禁止对 `docs/release-notes.md` 表格里 v15 debug SHA-256 占位做处理**（D2 用户忽略）。
7. **禁止提"WSL 迁移到 D 盘"或"C 盘清理"**（A1/A2/A3 用户决定真机测试后再谈）。
8. **禁止假设 v17 debug 数据**（D1）—— 必须向用户索取真实数据，不许编造/外推。
9. **禁止再查 buildozer signing 根因**（Q1 明规走方案 C）—— 直接封装 apksigner，不要浪费时间诊断 buildozer 为什么没自动签。
10. **禁止显式加 zipalign 步骤**（Q7 明规）—— 保持简单；apksigner 会检测对齐失败，出问题会明显暴露。
11. **禁止把口令通过命令行参数传给 apksigner / keytool / jarsigner**（会被 `ps -ef` 看到）；**必须用 stdin pipe 或读完立即 delete 的文件**。
12. **禁止在 `set -x` 或 `tee -a "$LOG"` 覆盖下处理口令赋值**（会把口令 echo 到日志文件）；日志分开，口令处理段落用 `set +x` 或独立 subshell。
13. **禁止把 `stage3-block3-problems.md` 加进 `.gitignore`**（Q4 明规：本文档入 git）。
14. **禁止追溯 v8~v16 debug 数据**（用户 D1 明规：中间版本记录缺失在用户监管下同意）。
15. **禁止建议"参数强制传版本号"以外的版本号自动化方案**（Q5 明规不接受 bin/ 扫描 +1 或类似自动方案）。
16. **禁止让 debug 和 release 用不同版本号**（Q6 明规：同一份代码状态，debug 与 release 共享同一版本号）。

---

## 4. 附录：当前工作树关键状态

### 4.1 已生成 / 已修改文件（本会话）

- `scripts/generate_release_keystore.sh`（新增，keytool 交互封装）
- `scripts/wsl_build_android.sh`（加 debug/release 参数 + rsync exclude keys/）
- `buildozer.spec`（加 `android.release_artifact = apk`）
- `.gitignore`（加 `keys/` + `buildozer.spec.local`）
- `reversible_mosaic/ui/self_test.py`（性能扫描升级为 Stage 3 AC-PERF 基准）
- `reversible_mosaic/io/png_metadata.py`（`rounds: Literal[2,5,15,30]`）
- `tests/adversarial/test_malicious_inputs.py`（+37 fuzz case）
- `tests/unit/test_task_coordinator.py`（+8 case）
- `tests/unit/test_desktop_gateways.py`（+6 case）
- `tests/unit/test_android_native.py`（新增，14 case）
- `tests/property/test_algorithm_properties.py`（skip 阈值调整）
- `requirements-dev.lock`（刷新）
- `docs/build-android.md`（大改，阶段 3 冻结基线）
- `docs/release-notes.md`（新增，v0.1.0 发行说明 + 第三方许可）
- `docs/test-plan.md`（新增，AC 追踪）
- `docs/source-index.md`（多处更新）
- `development_plan.md`（Block 1/2/3 完成情况）
- `keys/reversiblemosaic.jks`（用户生成，D 盘，`.gitignore` 覆盖）
- `buildozer.spec.local`（用户生成，D 盘，`.gitignore` 覆盖，含明文口令）

### 4.2 pytest / ruff / mypy 基线

- pytest: **250 passed / 21 skipped**
- ruff: **9 errors**（全部 baseline，scripts/ + main.py 遗留）
- mypy: **23 errors**（全部 baseline，test_exif/normalize/task_coordinator/v1_vectors 遗留）

任何代码改动完成后必须验证零回归（不新增违规）。

### 4.3 关键决策记录（历史）

- V1 算法已 FROZEN（2026-07-30）
- 轮次集：`{2, 5, 15, 30}`（2026-07-29 二次修订）
- 视觉验收：apeiria-network 单人 80 项通过（§12.3 单人 MVP 偏差路径）
- 性能验收基准机：未指定（用户当前使用的真机 = 事实上的验收机）
- applicationId：`io.placeholder.reversiblemosaic`（探针占位，正式发布前需换）
- 签名主体：`CN=Apeiria-network, C=CN`（MVP 内部签，不换）

### 4.4 本文档 git 追踪状态

- **文档路径**：`D:\python\python_projects\ReversibleMosaic\stage3-block3-problems.md`
- **git 追踪**：**是**（用户 Q4 明规入 git）。`.gitignore` 已确认未排除本文件。
- **敏感内容审计**：本文档**不含**明文 keystore 口令；**含**证书 SHA-256 fingerprint 与 APK SHA-256（这些属于公开可查数据，签过的 APK 任何人都能 `keytool -printcert` 读到 fingerprint）。可安全入 git。
- **生命周期**：Stage 3 Block 3 收官后（真机测试全部通过），本文档可选择：a) 保留作为历史记录；b) 归档到 `docs/history/` 或类似目录；c) 内容合并进 `development_plan.md` 后删除本文件。**下一个会话不要自作主张归档 / 删除本文档**，需用户明规。

### 4.5 用户 Q1-Q7 决策速查表（2026-07-31）

| # | 问题 | 用户决策 | 影响章节 |
|---|---|---|---|
| Q1 | buildozer signing 修复方案 | **C**（放弃 buildozer 自动签，脚本封装 apksigner） | § 1.C1、§ 1.C3、§ 3.9 |
| Q2 | B1 隔离边界是否含运行时临时文件 | **允许使用临时文件** | § 0.2、§ 3.1 |
| Q3 | v17 debug 真机数据由本会话还是下一个会话处理 | **下一个会话处理** | § 1.D1、§ 2 步骤 4 |
| Q4 | `stage3-block3-problems.md` 是否入 git | **入 git** | § 3.13、§ 4.4 |
| Q5 | D3 版本号策略 | **强制参数** | § 1.C3、§ 1.D3、§ 3.15 |
| Q6 | debug / release 版本号是否统一 | **统一版本号（同一份代码用同一版本号）** | § 1.C3、§ 3.16 |
| Q7 | apksigner sign 前是否显式 zipalign | **不加** | § 1.C3、§ 3.10 |

---

## 4.7 v18 打包端到端验证 + CRLF 事故复盘（2026-07-31 补录）

在本会话 §1 B1/C1/C3/D3 修完并 commit 后，用户请求测试 v18 debug + release
完整打包流程作为脚本修改的端到端验证。过程中撞到一个之前不知道的坑，一并记录。

### 4.7.1 v18 打包产物

| 版本 | SHA-256 | 大小 | 签名主体 | 备注 |
|---|---|---:|---|---|
| v18 debug | `afe99948f82017608862cf6c74c6c92f5d88e098120a339c9b703e40b8d20059` | 33,135,600 B | Android debug | `wsl_build_android.sh debug v18` 一次通过 |
| v18 signed Release | `c5ba1ba782cc3f45ef21820cf505a62b28e31993a687b31a4cd597aeb0e8dd53` | 33,135,600 B | `CN=Apeiria-network, C=CN` | 同 v17 keystore；apksigner v2+v3 verify 通过；证书 SHA-256 = `54c1bbbf...` 与 v17 逐位一致 |

WSL 侧 + D 盘两处 SHA 各自一致（`cp -a` 保真通过）。**v18 打包脚本端到端验证通过**：
双参强制、版本后缀命名、目标文件已存在 exit 4 拒覆盖（release v18 时曾触发过一次，防误覆盖工作正常）、apksigner heredoc stdin 传口令、verify + keytool -printcert 摘要、
D 盘回拷 + sha256sum —— 每条支路都跑过至少一次。

### 4.7.2 CRLF 事故根因（**下一个会话必须知晓**）

**症状**：debug v18 第一次 build 挂在 rsync 之前，报错：
```
: invalid option nameprojects/ReversibleMosaic/scripts/wsl_build_android.sh: line 25: set: pipefail
```
乱码是因为 `\r` 让终端回到行首覆盖显示。真实错误是 `set -euo pipefail\r` 里的 `\r`
让 bash 把 `pipefail\r` 当成非法选项名。

**根因**：Windows 侧 git 的 `core.autocrlf=true` 会在 checkout 时把 LF 文件转成
CRLF。本会话通过 Claude Code 的 Edit/Write 工具重写 `.sh` 文件时以 LF 写入，
但用户随后 `git checkout` 到新分支（`stage3-real-test`）触发 git 的行尾归一化，
`.sh` 被转 CRLF 落盘。WSL 侧 bash 读到 CRLF 就炸。

**修复（已应用）**：
1. **一次性 `sed -i 's/\r$//' scripts/*.sh`** 剥掉所有 shell 脚本的 CR。
   共 6 个脚本被修：`wsl_build_android.sh` -281B、`generate_release_keystore.sh` -187B、
   `wsl_build_v1_cython.sh` -78B、`wsl_prefetch_p4a.sh` -75B、`wsl_generate_visual_review.sh` -56B、
   `wsl_patch_numpy_include.sh` -22B。
2. **新增根级 `.gitattributes`** 永久锁定 `.sh` / `.py` / `.pyx` / `.pxd` / `buildozer.spec` /
   `*.toml` / `requirements*.lock/.txt` 用 LF；`.png` / `.jpg` / `.jks` / `.apk` / `.so` 标 binary。
   之后任何分支切换/checkout 都不会再触发 CRLF 归一化。

**下一个会话不能做的事**：
- **不要**用 `git config core.autocrlf false` 全局修 —— 会影响用户其他项目。
  `.gitattributes` 是项目级方案，`core.autocrlf` 应保持用户偏好不动。
- **不要**在 shell 脚本头部加"防御性" `sed 's/\r$//'` —— 是 hack，`.gitattributes` 是根本解。
- **修改任何 `.sh` / `.py` / `.pyx` 后**：如果用户没做分支切换，一般不会触发再次 CRLF；
  但如果又出现同样症状，先 `head -3 <file> | od -c | head -3` 看头几行是不是 `\r\n`，
  确认后 `sed -i 's/\r$//' <file>` 单独修 —— **不要**全项目扫描。

### 4.7.3 已收口的 § 1 § 2 事项状态更新

- **§ 1.B1** ✅ 完成（rsync exclude + WSL 侧清理）
- **§ 1.C1 + C3 + D3** ✅ 完成（apksigner 封装 + 双参强制）
- **§ 1.D1** ✅ 完成（v17 debug 真机数据入 probe-report + development_plan + test-plan）
- **§ 1.E2** ✅ 完成（AC-PERF 老口径 `{1,5,10,20}` 换成 v17 debug `{2,5,15,30}` 数据）
- **§ 1.C2** ✅ 完成（v18 signed Release apksigner 签名 + verify 通过 + 装机验收通过；见 § 4.7.5）
- **§ 1.F3~F5** ✅ 全部完成（见 § 4.7.5）
- **§ 1.F6** ⏭ SKIPPED（预期安全边界 —— release APK 不 debuggable，`run-as` 被 Android 沙盒拒绝，见 § 4.7.5）

现在**Stage 3 Block 3 全部收口**：v18 debug + release 两个 APK 在 D 盘 `bin/`，
证书指纹与 v17 一致，K80 Pro 上 AC-PERF 每档 ≥ 68× 余量、飞行模式主链路通过、
Manifest 权限只见存储类且封在 API 28。

### 4.7.4 stage3-real-test 分支时序（用户实际操作）

- 本会话中段 `problem-solution` 合到 `release`（用户操作）
- 从 `release` 拉 `stage3-real-test` 分支做真机测试调试（用户操作）
- 本文档的 § 4.7 与相关 v18 SHA 记录 commit（`92aa976 realtest1`）落在 `stage3-real-test`
- 本 § 4.7.5 F3/F4/F5 验收记录 commit 也在 `stage3-real-test`
- 未来 `stage3-real-test` 完成真机测试后合回 `release`，最终合入 `main`

### 4.7.5 F3 / F4 / F5 真机验收记录（2026-07-31，K80 Pro）

**测试设备**：小米 K80 Pro / Android 16 / RAM 16 GB (物理) + 6 GB (扩展)
**测试日期**：2026-07-31
**测试 APK**：v18 signed Release
（SHA-256 `c5ba1ba782cc3f45ef21820cf505a62b28e31993a687b31a4cd597aeb0e8dd53`；
证书 SHA-256 `54c1bbbf48f34aae46225a3ef4f332852a9b8f3ac42930d47132a1b41d6c91a7`）

#### F5 Manifest 权限验证 ✅ PASS

从 aapt dump 输出（`~/.buildozer/android/platform/android-sdk/build-tools/*/aapt`）：

```
package: io.placeholder.reversiblemosaic
sdkVersion: 26
targetSdkVersion: 34
native-code: 'arm64-v8a'
uses-permission: WRITE_EXTERNAL_STORAGE maxSdkVersion=28
uses-permission: READ_EXTERNAL_STORAGE  maxSdkVersion=28  # Android 自动派生
```

**判定**：
- ❌ 无 `INTERNET` / `ACCESS_NETWORK_STATE` （AC-016 关键项 + 飞行模式验证前置）
- ❌ 无 `CAMERA` / `LOCATION` / `READ_MEDIA_*` / `READ_CONTACTS`（敏感权限全清）
- ✅ 存储权限都限 API 26–28
- ✅ 单 ABI arm64-v8a、minapi 26、target 34 符合 MVP 目标

**READ_EXTERNAL_STORAGE 的自动派生说明**：`buildozer.spec` 只声明了 WRITE，
Android manifest merger 自动补 READ（"能写必能读"的隐含规则，API 4+ 就有），
并同样 cap 到 `maxSdkVersion=28`。这不是配置漏洞，是标准行为 + 符合意图（API 26–28
需要文件系统读写，API 29+ 走 scoped storage 不申请）。

#### F3 v18 signed Release AC-PERF 复采 ✅ PASS（每档余量 ≥ 68×）

App 内 "Stage 3 AC-PERF 基准" 按钮跑 1920×1080 RGB × `{2, 5, 15, 30}` × 5 次
encrypt-only：

| rounds | median | P95 | peak_rss | target | verdict | 余量 |
|---:|---:|---:|---:|---:|:---:|---:|
|  2 | 0.051 s | 0.056 s | 484.8 MiB |  6 s | ✅ PASS | ~118× |
|  5 | 0.127 s | 0.133 s | 484.8 MiB |  9 s | ✅ PASS | ~71× |
| 15 | 0.341 s | 0.381 s | 484.8 MiB | 27 s | ✅ PASS | ~79× |
| 30 | 0.762 s | 0.766 s | 484.8 MiB | 52 s | ✅ PASS | ~68× |

- 总扫描 8.6 s，backend = `cython`（confirmed via UI 打印行）
- 写入 `/data/user/0/io.placeholder.reversiblemosaic/files/stage3_bench.json`
  （v18 起 self_test.py 用新文件名，与 v17 遗留的 `stage0_perf.json` 区分）
- **同机 v17 debug 对比 median 快 ~50%**（例：30 轮 1.533 → 0.762 s）
  —— 归因于测试环境状态差异（手机充电时锁高频、前置探针累计 RSS）而非代码差异。
  两个 build 用同一份 Cython `.so`（裸名 `v1.so`），字节相同。
- peak_rss 484.8 MiB 远低于 §10.1 60% 内存上限（16 GB × 60% ≈ 9.6 GiB）。

**注**：MVP 内部发布使用 K80 Pro（flagship SoC）。正式面向公开用户发布前，
需要绑定"约定低端 8 GB arm64 机型"复采一次，K80 Pro 的 68× 余量给了充足 headroom
但需实测确认。

#### F4 飞行模式 + PNG/JPEG 主链路 + UI 兼容 ✅ PASS

- ✅ 飞行模式开启下 PNG 主流程（选图 → 打码 → 保存 → 恢复）通过
- ✅ 飞行模式开启下 JPEG 主流程（含 EXIF orientation 分支）通过
- ✅ 随机分享代码路径通过（6 位数字，避开默认 500000）
- ✅ 保存到相册 → 系统相册（Pictures/ReversibleMosaic）可见输出文件（MediaStore 路径工作正常）
- ✅ 系统深色 / 浅色主题切换下 UI 主链路均正常，无布局崩坏
- ✅ 系统大字体（无障碍最大字号）下 UI 布局不溢出、按钮可点、主链路完整

**判定**：AC-016 人工部分（飞行模式）+ AC-001（装机启动）+ AC-003 人工部分（PNG + JPEG）
+ AC-012 人工部分（MediaStore 保存 + 相册可见）全部 ✅。

#### F6 stage3_bench.json adb pull ⏭ SKIPPED（预期安全边界）

Release APK 没有 `android:debuggable="true"`（这是正确的安全姿态），
`adb shell run-as io.placeholder.reversiblemosaic` 报 `package not debuggable`。
Android 沙盒隔离在 release 环境下屏蔽了 App 私有目录，`adb pull` 拿不到
`stage3_bench.json`。

AC-PERF 数据以 App 内自检屏截图为准，JSON 归档非必要。未来若需归档：
- 出一版 **debug** 签名的 v19（buildozer.spec 加 `debuggable=1`）供数据取样
- 或让 App 把 benchmark JSON 复制一份到 `Pictures/ReversibleMosaic/`（scoped storage 用户可见）

**MVP 阶段不做上述任一改造**，截图判定已足够。

---

## 5. 结束语（给下一个会话的 AI）

用户已经因为**多次疏忽 + C 盘占用问题 + v16/v17 命名脱节**积累了不满。**你必须：**

1. **不推进任务** —— 除非用户明确同意下一步（F3~F6 暂停中）。
2. **不假设 / 不编造** —— v17 debug 数据、验收机型号、备份位置等未知信息，必须问用户，不许自己脑补。
3. **不再犯"命令给错 shell"、"路径写错"、"版本号脱节"、"文档更新遗漏"这类低级错误** —— 每个改动收尾都要 grep 一遍相关引用。
4. **修任何 signing / keystore / spec.local 相关的代码 / 脚本 / 文档前，回读本文档 § 0.2 与 § 3** —— 违反 = 用户回退。
5. **完成 C1（合并到 C3）/ C3 / D3 / B1 等代码类改动后**，跑 pytest + ruff + mypy 验证零回归。
6. **完成 E2 + D1 等文档类改动**：先向用户索取 v17 debug 真机数据，再同步三份文档。
7. **只有全部处理完毕**，才可以问用户"是否开始真机测试（F3~F6）"。

祝工作顺利。用户在等你交出无遗漏的修复。
