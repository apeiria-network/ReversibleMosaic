# V1 算法规范（冻结前草案）

> 状态：**实验草案，2026-07-29 定稿基础参数。固定向量和视觉阈值仍需
> 3 人验收前完成冻结。发布后改变像素行为必须注册 V2。**

## 1. 输入契约

- 行优先、C-contiguous 的 `uint8` 矩阵。
- 模式仅为 RGB（3 通道）或 RGBA（4 通道）。
- 种子范围 `0..9999999999`。
- 轮数仅为 `2/5/10/20`（2026-07-29 修订，原 `1/5/10/20`）。
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

## 9. 冻结前待办

- ✅ V1 定稿参数：`R = max(8, min(W,H)//32)`, `rounds = {2, 5, 10, 20}`,
  单 pass 100% density（2026-07-29）
- ✅ 将参考实现与 Cython 优化实现逐字节对照（`tests/unit/test_optimized_v1.py`，
  Linux/CI 强制）
- ✅ 固定向量草案 `tests/vectors/algorithm_v1_draft.json`（2026-07-29 重生）
- ⏳ 固定视觉图集，测量像素变化率、相邻相关性和边缘相似度（`metrics.json`）
- ⏳ 完成人工视觉验收后冻结阈值和发布日期（`docs/algorithm-v1.md` 状态翻 frozen）

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
   越大。R=93（p9 尺寸下）时，单轮期望位移覆盖 min 边的 6%；20 轮
   累积覆盖 min 边的 ~62%，图片主体被打散。

### A.5 严格逆向

正向按 `(y, x) = (0, 0), (0, 1), ..., (H-1, W-1)` 扫描；逆向按 `(y, x) =
(H-1, W-1), ..., (0, 0)` 反扫描。同一 PRF 派生同一 `j`，同一 `j > i`
判定，同一 swap 操作。

**为什么反扫描能还原**：正向按索引升序访问，每对 `{i, j}` 在 `min(i, j)`
被访问时触发一次。反扫描按索引降序，同一对在 `max(i, j)` 被访问时**再
触发一次**——两次交换正好抵消，恢复原状。

多轮：正向 `for r in range(rounds)`，逆向 `for r in range(rounds - 1, -1, -1)`。

### A.6 为什么允许 2/5/10/20 轮？（不再是 1/5/10/20）

**为什么 1 轮被删除**：V1 单轮扫描时每像素最多位移 R = min 边 //32。对于
2000+ 像素宽的真实照片，1 轮位移 = 3% 图宽，视觉上几乎看不出改动。
"sanity check 层"应该是"用户明显能看出图片被处理了"，2 轮位移到 6%
才有这个观感。所以 V1 最低设为 2。

- **2 轮**：sanity check——用户明确能看出图片被扰动了，但主体还清晰
- **5 轮**：MVP 默认——特征明显模糊，主体轮廓仍可辨
- **10 轮**：主要色块可见但细节混乱
- **20 轮**：完全打散，只剩色调是原图的

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
| 允许轮数 | `{2, 5, 10, 20}` | `VALID_ROUNDS` |

冻结锚点在 `tests/vectors/algorithm_v1_draft.json`（PC 生成一次、跨平台
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

阶段 1 真机基准（**旧 V1 with lift + permute + diffuse**，1920×1080 RGB, 5 次
中位数, v7 APK, `registry V1 backend = cython`, 2026-07-28）：

| 轮数 | 实测 median | 实测 p95 | AC-PERF 上限 | 余量 |
|---|---|---|---|---|
|  1 | 0.060 s | 0.062 s |  3.0 s | 50× |
|  5 | 0.268 s | 0.368 s |  ~9.0 s | 34× |
| 10 | 0.543 s | 0.611 s | 18.0 s | 33× |
| 20 | 1.072 s | 1.133 s | 35.0 s | 32× |

**新 V1**（当前，2026-07-29 定稿）与旧 V1 的每轮工作量：
- 旧 V1：4 sub-ops per round × 20 轮 = 80 sub-ops
- **新 V1：1 sub-op per round × 20 轮 = 20 sub-ops**（**至少快 4×**）

预估新 V1 Cython 真机耗时（1920×1080 20 轮）：**~0.27s**，AC-PERF 目标
35s 有 130× 余量。真机基准需在 v8 APK 上重跑验证。

峰值 RSS 274.7 MiB（覆盖 3 份 1920×1080×3=18.6 MiB 全分辨率缓冲 + 64 MiB
固定开销 + Kivy 运行时）。
