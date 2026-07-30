# V1 算法规范

> 状态：**FROZEN**（2026-07-30 冻结，rounds `{2, 5, 15, 30}`, R=max(8,//32)）。
> 视觉验收由 apeiria-network 于 2026-07-30 单人签署，自动指标阈值同日冻结
> ([artifacts/visual_review/scorecard.md](../artifacts/visual_review/scorecard.md),
> [§A.13](#a13-自动指标冻结阈值)）。发布后改变像素行为必须注册 V2。

## 1. 输入契约

- 行优先、C-contiguous 的 `uint8` 矩阵。
- 模式仅为 RGB（3 通道）或 RGBA（4 通道）。
- 种子范围 `0..9999999999`。
- 轮数仅为 `2/5/15/30`（2026-07-29 定稿，经 `1/5/10/20` → `2/5/10/20` →
  当前值两次迭代）。
- 所有算术均按模 256（像素通道）或模 `2^64`（64 位参数）。

## 2. 参数派生

根输入为 ASCII 域标签 `reversible_mosaic/algorithm/v1\0`，随后拼接：

1. `seed`：LE64；
2. `width`：LE32；
3. `height`：LE32；
4. `algorithm_version=1`：LE32；
5. `mode_id`：RGB=3、RGBA=4，单字节。

对根输入计算一次 SHA-256，按小端拆为 4 个 64 位 word（`words[0..3]`）。V1
仅使用 `words[1]` 作为置换主密钥；其他三个 word 保留用于未来 P1
色彩变换加强模式的密钥派生，避免届时需要修改哈希域。

轮密钥：
```
round_key(word, r, domain) = SplitMix64(word ⊕ (r × 0xD1342543DE82EF95) ⊕ domain)
```
V1 只使用 `domain = 0x22`（继承原草案的 permute 阶段标签），确保参数派生
稳定。

## 3. 邻域半径

```
R = max(8, min(W, H) // 32)
```

- 小图（min 边 ≤ 256）：R 固定为 8，避免"1×N 长条 R=0"退化。
- 大图：R 自适应到 min 边的 ~3.1%（因此不同尺寸图在相同 rounds 下视觉
  体验一致）。

## 4. 单轮正向（唯一子操作：邻域交换）

对每个像素 `i = y*W + x`（扫描序 y=0..H-1, x=0..W-1）：

```
offset = SplitMix64(round_key ⊕ i)
dy_raw = (offset >> 32) mod (2R+1)      # 0..2R
dx_raw = (offset       ) mod (2R+1)     # 0..2R
yj = (y + dy_raw + H - R) mod H         # dy 落入 [-R, +R] 后模 H 环绕
xj = (x + dx_raw + W - R) mod W         # dx 同理
j = yj*W + xj
if j > i:
    swap(pixels[y, x, :], pixels[yj, xj, :])   # RGBA 全通道一起交换
```

**canonical direction**：只在 `j > i` 时交换，保证每对无序对至多触发一次
（从更小索引的成员发起）。

## 5. 严格逆向

反向扫描 `y = H-1..0`，`x = W-1..0`，同样 PRF 派生 `j`，同样 `j > i` 判定，
同样 swap。反向扫描保证：处理 `i` 时它的原配对目标 `j > i` 尚未被"取消"，
从而正确回滚。

多轮：正向 `for r in range(rounds)`，反向 `for r in range(rounds - 1, -1, -1)`。

## 6. 关键性质

1. **调色板保留**：只是位置改变，像素 RGB(A) 值本身从未被算术修改。encrypted
   图片的 RGB 频度分布与原图**逐字节相等**。
2. **Alpha 语义**：作为像素单位跟随 RGB 一起移动，从不被单独修改。透明像素
   （Alpha=0）中的 RGB 完整保留，恢复后仍是原始值。
3. **确定性**：给定 `(input, seed, rounds)` 输出字节唯一；无 `hash()`
   随机化、无平台/线程依赖。
4. **可逆**：`decrypt(encrypt(I))) == I` 逐字节相等。
5. **无色彩雪崩**：单像素输入改动只影响自身位置（而非通过 diffuse 链条
   影响后续像素）。V1 定位为视觉扰乱，不是密码学加密（§11.2 明示）。

## 7. 边界与低信息图片

- **1×1 图**：邻域坍缩到自身，`j = i = 0`，无 swap。encrypted = 原图（identity）。
- **1×N / N×1 长条**：H 或 W 为 1 时，dy 或 dx 通过模 1 环绕全为 0，只沿另一
  方向做 swap。仍逐字节可逆。
- **单一颜色纯色图**：所有 swap 都是"同值对同值"，encrypted = 原图。
- **§12.3.5 豁免**：纯色 / 1×1 / 全透明图只验收可逆性，不参与视觉隐藏能力
  打分。

## 8. P1 加强模式（预留，不接入 MVP）

可选叠加 [color_transform.py](../reversible_mosaic/core/algorithm/color_transform.py)
的 `lift_forward` + `diffuse_forward` 作为"更强隐私模式"，破坏调色板保留
特性以获得更强抗视觉恢复。**MVP 默认关闭**；UI 加开关后作为 P1 版本发布。
详见需求档 §3.3 P1 条目。

## 9. 冻结记录

**V1 冻结日**：2026-07-30。所有验收条目已通过：

- ✅ V1 定稿参数：`R = max(8, min(W,H)//32)`, `rounds = {2, 5, 15, 30}`,
  单 pass 100% density（2026-07-29 二次修订，加大主档/最高档预算）
- ✅ 参考实现与 Cython 优化实现逐字节对照（`tests/unit/test_optimized_v1.py`，
  Linux/CI 强制）
- ✅ 固定向量 [tests/vectors/algorithm_v1.json](../tests/vectors/algorithm_v1.json)
  （2026-07-30 冻结，status: frozen）
- ✅ 固定视觉图集，测量像素变化率、相邻相关性和边缘相似度
  （[artifacts/visual_review/metrics.json](../artifacts/visual_review/metrics.json)）
- ✅ 自动指标冻结阈值（§A.13，基于实测均值 + 15-20% 留白）
- ✅ 人工视觉验收：20 图 × 4 轮 × default seed = 80 项打分。**全部四档
  通过发布决策规则**（2 轮 20/20, 5 轮 19/20, 15 轮 16/20, 30 轮 20/20；
  详见 [scorecard.md](../artifacts/visual_review/scorecard.md)）

---

## 附录 A：面向读者的算法讲解

上面 1–7 节是给验证者看的严格规范。这一节是给"想弄明白 V1 到底在做什么"的
读者看的说明；对照 [reference_v1.py](../reversible_mosaic/core/algorithm/reference_v1.py)
逐行读。

### A.1 一句话概括

V1 是**逐像素、逐字节可逆的空间置换变换**——把一张 8-bit RGB/RGBA 图像的
像素**位置**在小邻域内随机重排，凭"算法版本 + 轮数 + 分享代码"这三件套
可以逐字节还原原图。**颜色调色板完全保留**：encrypted 图与原图有完全
相同的颜色频度分布，只是每个像素被搬到了别的位置。

它**不是加密**：算法开源，任何人都能穷举 100 亿个分享代码；它也不带 MAC，
改一位 encrypted 像素再解密依然会得到一张"看起来是图"的东西。它只提供
两件事：

- **可逆性**：给对参数就能一比特不差地还原
- **视觉扰乱**：肉眼看不出原图内容

需求档 §11.2 把这些非目标写得很清楚。

### A.2 输入与规范化

进入算法前，图片会被规范化成一个 numpy 矩阵：

```
I : uint8[H][W][C]     # C = 3 (RGB) 或 4 (RGBA)
```

JPEG 的 EXIF Orientation 1–8 会先应用一次，输出到算法前的所有像素都已经
"摆正"了。算法看不到文件字节，也不关心 EXIF/ICC/文件名——它只吃这个矩阵。

### A.3 从"分享代码"到"轮密钥"

用户看到的**分享代码**是 1–10 位十进制数字（默认 `500000`）。去前导零后
成为**扰动种子** `s ∈ [0, 9_999_999_999]`。

第一步：把种子和图片规格拼成一段 43 字节的确定性负载，做一次 SHA-256，
切成 4 个 64-bit 主密钥字。V1 只用 `words[1]` 作为置换密钥；其他三个
预留给未来 P1 色彩变换。

```
payload = "reversible_mosaic/algorithm/v1\0"      # 31 B 域分离标签
        || LE64(seed)                              # 8 B
        || LE32(width) || LE32(height)             # 8 B
        || LE32(1)                                 # 4 B  algorithm_version
        || LE8(mode_id)                            # 1 B  RGB=3, RGBA=4

(K0, K1, K2, K3) = split(SHA256(payload), 64bit x 4)   # 小端
```

**"域分离标签"**的作用：即使别的软件也用 SHA-256 派生参数，只要不带这串
固定字节，就一定得到不同的密钥。种子改一位、宽高改一像素、RGB↔RGBA
切换——四个 K_i 全变。

第二步：每一轮 r（r = 0, 1, ..., n-1）用 SplitMix64 快速 PRF 派生该轮的
置换子密钥：

```
tau_swap = 0x22
k_swap_r = splitmix64( K1 XOR (r * 0xD1342543DE82EF95) XOR tau_swap )
```

SplitMix64 本身是三步 64-bit 整数混合（Guy L. Steele Jr. et al. 2014），
不是密码学 PRF，但雪崩性够好、速度极快。作用就是"给定一个整数索引，喷
一段确定性的伪随机字节"。

### A.4 单轮变换：邻域交换

把矩阵铺平成 N = H×W 个"像素行"（RGB 三通道或 RGBA 四通道一起视作一个
不可分割的单位）：

```
flat = I.reshape(N, C)
```

**关键设计**：不做任何色彩变换（不 lift、不 diffuse），只做**空间上的
位置交换**。每个像素独立决定它想与谁互换：

```
R = max(8, min(W, H) // 32)     # 邻域半径, 自适应

for y in 0..H-1:
    for x in 0..W-1:
        i = y * W + x
        # 派生 (dy, dx), 各在 [-R, +R] 范围
        offset = splitmix64(k_swap ^ i)
        dy = (offset >> 32) mod (2R+1) - R
        dx = (offset       ) mod (2R+1) - R
        # 环绕到图内位置
        yj = (y + dy) mod H
        xj = (x + dx) mod W
        j = yj * W + xj
        if j > i:                            # canonical direction
            swap(flat[i], flat[j])           # 整像素交换
```

**canonical direction**（只在 `j > i` 时交换）保证：每对无序对 `{i, j}`
只被触发一次（从更小索引的成员发起，避免"i→j 再 j→i"抵消）。

**这样做的性质**：

1. **调色板保留**：pixel[i] 从来没有被算术修改，只是从位置 (y, x) 搬到
   位置 (yj, xj)（或者作为交换的另一方，从 (yj, xj) 搬到 (y, x)）。
   sorted(encrypted.flatten()) == sorted(original.flatten())。

2. **Alpha 语义**：RGBA 作为完整像素单位交换，Alpha 从不被单独修改。透明
   像素（α=0）中的 RGB 完整保留。

3. **视觉效果**：轮数 r 越大，同一像素被交换的次数期望越多，累积位移
   越大。R=93（p9 尺寸下）时，单轮期望位移覆盖 min 边的 6%；30 轮
   累积覆盖 min 边的 ~76%（random-walk-like，∝ sqrt(rounds)），图片
   主体被打散。

### A.5 严格逆向

正向按 `(y, x) = (0, 0), (0, 1), ..., (H-1, W-1)` 扫描；逆向按 `(y, x) =
(H-1, W-1), ..., (0, 0)` 反扫描。同一 PRF 派生同一 `j`，同一 `j > i`
判定，同一 swap 操作。

**为什么反扫描能还原**：正向按索引升序访问，每对 `{i, j}` 在 `min(i, j)`
被访问时触发一次。反扫描按索引降序，同一对在 `max(i, j)` 被访问时**再
触发一次**——两次交换正好抵消，恢复原状。

多轮：正向 `for r in range(rounds)`，逆向 `for r in range(rounds - 1, -1, -1)`。

### A.6 为什么允许 2/5/15/30 轮？

**演变历程**：`{1, 5, 10, 20}`（原草案）→ `{2, 5, 10, 20}`（2026-07-29 一次
修订，删掉 1 轮因为位移 <3% 图宽不算 sanity check）→ `{2, 5, 15, 30}`
（2026-07-29 二次修订，主档 10→15、最高档 20→30 各加 50% 预算，因为原
10/20 轮档在少数内容丰富图上仍能勉强辨认轮廓）。

- **2 轮**：sanity check —— 遮盖细节（纹理、小文字、小物件、装饰），
  主体轮廓允许仍可识别
- **5 轮**：MVP 默认 —— 较难辨认；主体需仔细看才能识别，文字不可读，
  人脸细节丢失
- **15 轮**：主档 —— 无法直接辨认主体 / 文字 / 人脸
- **30 轮**：最高档 —— 无法直接辨认（同 15 轮，但累积位移更彻底，
  作为保险档）

需求 §12.3.6 要求：如果同一分享代码在 ≥3 张内容丰富图上都失败视觉验收，
则视为参数派生规则有系统性退化，V1 不得发布。

### A.7 Alpha 通道的三条约定

需求档 §5.7 / §5.8 / §7.3.9：

1. **Alpha 值不被读、不被修改、不被与 RGB 混合**——V1 只做位置交换，
   本身不涉及任何通道级算术，Alpha 自然被完整保留
2. **Alpha 随空间置换共同移动**——swap 是整像素 swap，Alpha 与 RGB 一
   起搬迁
3. **透明像素（α=0）中的 RGB 必须保留**——由 (1) + (2) 自然满足，无需
   特殊代码路径

代码上体现在：`_neighborhood_swap_forward` / `_neighborhood_swap_inverse`
对 `pixels[y, x, :]` 整行操作，从不单独触碰任何通道。

### A.8 可逆性的直觉证明

**命题**：对任意合法的 `(version, seed, rounds, I)`，
`decrypt(encrypt(I)) == I`（逐字节相等）。

**为什么成立**：

1. 每一轮的正向 = 一组按扫描序触发的 swap
2. 每一轮的逆向 = 同一组 swap 但按反扫描序触发
3. swap 是**自逆对合**（involution）：swap(a, b) ∘ swap(a, b) = identity
4. 所以正向轮 ∘ 逆向轮 = identity
5. 多轮 = n 个可逆变换的复合 = 可逆

"逐字节相等"是需求档 AC-008 的最硬指标，`tests/property/` 和
`tests/vectors/` 都在覆盖它。

### A.9 边界尺寸的处理

需求 §5.9 要求"边缘和小尺寸必须采用可逆规则，不得裁剪或以补值替代
原像素"。

看代码：邻域交换用模 H / 模 W 环绕（`(y + dy) mod H`, `(x + dx) mod W`），
从不越界访问。所以：

- **1×1**：只有一个像素，H=W=1，dy 和 dx 通过模 1 全为 0，`j = i`，
  条件 `j > i` 不满足，无 swap。encrypted = 原图（identity），仍可逆。
- **1×N、N×1**：一维长条，短边为 1 的方向 dy 或 dx 通过模 1 归零。仍
  在另一方向做正常 swap。
- **奇数尺寸**：无特殊分支，模 H / 模 W 环绕自然处理。
- **纯色**：swap 是"同值对同值"，视觉上等同 identity；但算法层面仍
  确定性执行，palette 保留（trivially）。

这些 corner case 在 `tests/unit/test_algorithm_v1.py` 和
`tests/property/test_algorithm_properties.py` 里都有覆盖。

### A.10 冻结常量清单

到 V1 冻结日为止，以下常量**永远不能改**（改了必须叫 V2）：

| 名字 | 值 | 出处 |
|---|---|---|
| 域分离标签 | `"reversible_mosaic/algorithm/v1\0"` | `_derive_words` |
| SplitMix64 加常数 | `0x9E3779B97F4A7C15` | `_splitmix64` |
| SplitMix64 乘常数 A | `0xBF58476D1CE4E5B9` | `_splitmix64` |
| SplitMix64 乘常数 B | `0x94D049BB133111EB` | `_splitmix64` |
| 轮索引乘子 | `0xD1342543DE82EF95` | `_round_key` |
| 置换阶段标签 | `0x22` | `_SWAP_DOMAIN` |
| 半径公式 | `max(8, min(W,H) // 32)` | `_radius_for` |
| 单轮扫描方向 | 正向 y=0..H-1, x=0..W-1 | `_neighborhood_swap_forward` |
| canonical swap 判定 | `j > i` | `_neighborhood_swap_forward` |
| 分享代码上限 | `9_999_999_999`（10 位十进制） | `_derive_words` |
| 允许轮数 | `{2, 5, 15, 30}` | `VALID_ROUNDS` |

冻结锚点在 `tests/vectors/algorithm_v1.json`（PC 生成一次、跨平台
diff）。任何一处改动都会让 `test_v1_vectors.py` 立刻变红。

### A.11 非目标（重申）

1. **不是加密**：源码开源 + 分享代码空间只有 10^10，任何人都能穷举
2. **不隐藏元数据**：PNG tEXt 里明文写 `algorithm_version` / `rounds` /
   `pixel_mode`（但**绝不写 seed**）
3. **抗篡改能力 = 0**：不带 MAC，改一位密文也能"解密"，只是得到错的
4. **社交平台重压缩不保**：微信 / 微博 / QQ 空间会重编 JPEG → 像素被有损
   → 解密出乱码
5. **不用 Python `hash()`**：CPython 的 `hash(str)` 加了 PYTHONHASHSEED
   随机化，跨进程不可复现；V1 全用 SHA-256 + SplitMix64，跨设备位一致
6. **调色板保留不是密码学优势**：由于 encrypted 与原图有相同的颜色频度
   分布，理论上可从直方图推断"图里大概有什么颜色"。但对视觉扰乱够用。
   如果需要"看起来完全无关"，等 P1 加强模式（叠加色彩变换）。

### A.12 性能画像

| 层 | 实现 | 当前状态 |
|---|---|---|
| 规范代表 | [reference_v1.py](../reversible_mosaic/core/algorithm/reference_v1.py) 纯 Python | 慢，作为跨平台 oracle |
| 优化候选 | `v1.pyx` Cython（`nogil` 释放 GIL） | 阶段 1 已接入生产（`optimized_v1.py` + `registry.py` fallback）|
| Pipeline 集成 | **阶段 1 v7 完成 + 阶段 2 V1 重写完成** | `registry.get(1)` 优先返回 Cython 后端；PC/CI 无 Cython 时自动退回 reference |

**新 V1 真机基准**（v8 APK, 1920×1080 RGB, 5 次中位数,
`registry V1 backend = cython`, 2026-07-29 一次修订：`{2,5,10,20}` 数据）：

| 轮数 | 实测 median | 实测 p95 | AC-PERF 上限 | 余量 |
|---|---|---|---|---|
|  2 | 0.103 s | 0.109 s |  ~6.0 s | 58× |
|  5 | 0.257 s | 0.260 s |  ~9.0 s | 35× |
| 10 | 0.512 s | 0.515 s | 18.0 s | 35× |
| 20 | 1.022 s | 1.023 s | 35.0 s | 34× |

**当前 `{2,5,15,30}` 预估（线性外推 v8 数据，等新 APK 实测替换）**：

| 轮数 | 预估 median | AC-PERF 上限（§10.2 修订） | 余量 |
|---|---|---|---|
|  2 | ~0.10 s |  ~6.0 s | 60× |
|  5 | ~0.26 s |  ~9.0 s | 35× |
| 15 | ~0.77 s | 27.0 s | 35× |
| 30 | ~1.53 s | 52.0 s | 34× |

15/30 轮预估基于 V1 单轮成本恒定的性质（每轮扫描全部像素 1 次，无 chain
dependencies）。真机实测需在下一 APK 重跑验证。

对比阶段 1 v7（**旧 V1: lift + permute + diffuse**, 2026-07-28）——同 1920×1080 /
Cython / 5 次中位数：v7 20 轮 = 1.072 s，v8 20 轮 = 1.022 s。每轮子操作从
3 降到 1，但 pixel-level PRF + swap 的绝对成本比原 one-pass permute shuffle
高，两者互相抵消，实际耗时基本持平（v8 略胜 ~5%）。之前"至少快 4×"的
乐观预估未成立；不影响 AC-PERF，34× 余量已经充分。

峰值 RSS 422 MiB（v8 完整 App 运行时，包含 Photo Picker + PIL RGBA/JPEG
codec + Kivy）；纯算法内存部分仍为 3 × 1920×1080×3 ≈ 18.6 MiB，与 v7 一致。

### A.13 自动指标冻结阈值

三项指标（需求档 §12.3.3）在 2026-07-29 二次修订定稿 V1（rounds `{2,5,15,30}`）
上跑 20 张固定图集（`artifacts/visual_review_sources/`）× 4 轮 × default seed，
测得下列均值。冻结阈值取"实测均值 + 单向留白 15-20%"作为**验收下限**——
低于阈值即视为算法退化，V1 不得发布。

| 轮数 | 指标 | 实测均值 | **冻结阈值** | 判定方向 |
|---|---|---|---|---|
|  2 | pixel_change_rate     | 0.791 | **≥ 0.65** | 越高越扰乱 |
|  2 | \|corr\|_worst_of_hvd | 0.581 | **≤ 0.75** | 越低越扰乱 |
|  2 | edge_similarity       | 0.184 | **≤ 0.28** | 越低越扰乱 |
|  5 | pixel_change_rate     | 0.886 | **≥ 0.75** | 越高越扰乱 |
|  5 | \|corr\|_worst_of_hvd | 0.472 | **≤ 0.60** | 越低越扰乱 |
|  5 | edge_similarity       | 0.161 | **≤ 0.22** | 越低越扰乱 |
| 15 | pixel_change_rate     | 0.913 | **≥ 0.80** | 越高越扰乱 |
| 15 | \|corr\|_worst_of_hvd | 0.331 | **≤ 0.45** | 越低越扰乱 |
| 15 | edge_similarity       | 0.143 | **≤ 0.20** | 越低越扰乱 |
| 30 | pixel_change_rate     | 0.927 | **≥ 0.82** | 越高越扰乱 |
| 30 | \|corr\|_worst_of_hvd | 0.243 | **≤ 0.35** | 越低越扰乱 |
| 30 | edge_similarity       | 0.136 | **≤ 0.18** | 越低越扰乱 |

**vs 一次修订 `{2,5,10,20}` 数据的改善**：pixel_change_rate 与 edge_similarity
基本饱和（图集信息熵限制），主要靠位移覆盖增加降低 `|corr|_worst_of_hvd`：
- 主档：10→15 轮，均值 0.383→0.331（-13.6%），outlier p4 max 0.716→0.505
- 最高档：20→30 轮，均值 0.293→0.243（-17.1%），outlier p4 max 0.716→0.386

**判定口径**：

1. 每一档取 20 张图的**均值**（不是极值），因为个别低信息图（大面积
   平滑渐变、如 p4 4096×3072 天空图）即便打乱后邻域相关性仍高，属于
   信息熵限制，不代表算法失效。§12.3.5 已豁免这类图的视觉隐藏能力
   评分；自动指标也按同口径处理。
2. `|corr|_worst_of_hvd` = `max(|horizontal|, |vertical|, |diagonal|)`
   逐图取最坏方向后再对 20 图求均值。
3. 三项指标必须**同时**通过所在轮次的阈值。任一项在任一轮次不达标 →
   V1 不得发布，回归定位。
4. 三个 seed（default / secondary_a / secondary_b）都必须独立通过；
   任一 seed 全线失败 → §12.3.6 系统性退化，V1 不得发布。

**留白依据**：均值到阈值的距离约 15-20%，允许后续加入不同风格的测试图
时轻微漂移（例如新增更多低信息图），但足够检测 20% 以上的算法退化
（例如 R 半径误改小、轮次少扫、某轮 no-op）。

**冻结签署**：2026-07-30，apeiria-network 单人视觉验收签署，V1 status → frozen；
数值一经冻结改动必须叫 V2（§A.10 冻结常量清单）。
