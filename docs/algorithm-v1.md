# V1 算法规范（冻结前草案）

> 状态：**实验草案，尚未公开发布，固定向量和质量阈值尚未冻结。**
> 任何实现或测试调整均须在首次发布前完成；发布后改变像素行为必须注册 V2。

## 1. 输入契约

- 行优先、C-contiguous 的 `uint8` 矩阵。
- 模式仅为 RGB（3 通道）或 RGBA（4 通道）。
- 种子范围 `0..9999999999`。
- 轮数仅为 `1/5/10/20`。
- 所有通道算术均按模 256；64 位参数算术按模 `2^64`。

## 2. 参数派生

根输入为 ASCII 域标签 `reversible_mosaic/algorithm/v1\0`，随后拼接：

1. `seed`：LE64；
2. `width`：LE32；
3. `height`：LE32；
4. `algorithm_version=1`：LE32；
5. `mode_id`：RGB=3、RGBA=4，单字节。

对根输入计算一次 SHA-256，并按小端拆为 4 个 64 位 word。各轮通过规范中定义的 SplitMix64 finalizer、轮索引及用途域派生 lifting、置换、正向扩散和反向扩散 key。派生次数固定，不按种子数值循环。

## 3. 单轮正向

1. **RGB lifting**：逐像素执行三步模 256 三角加法；位置掩码由 key 与像素索引派生。Alpha 不读取。
2. **空间置换**：对完整像素执行 Fisher–Yates，索引从 `N-1` 降到 1。随机 64 位值通过乘法高半部映射到 `[0,i]`，避免取模偏差。RGBA 四通道共同交换。
3. **正向扩散**：行优先从首像素到尾像素，RGB 加上前一输出像素的交叉通道和位置掩码。
4. **反向扩散**：使用独立 key 从尾像素到首像素执行同构扩散。

## 4. 严格逆向

每轮按反向扩散逆、正向扩散逆、置换逆、lifting 逆执行；多轮从最后一轮回退。置换逆无需索引表，按索引 1 到 `N-1` 重新生成相同交换。

## 5. Alpha 语义

- Alpha 值不参与 RGB 混合且不被算术修改。
- 空间置换时 RGBA 作为完整像素共同移动。
- Alpha=0 的 RGB 仍参与完整算法，并须逐字节恢复。
- 缩略图或 UI 纹理不得回写算法矩阵。

## 6. 冻结前待办

- 建立阶段摘要和固定向量 JSON。
- 将参考实现与 Cython 优化实现逐字节对照。
- 对 1–20 轮与小尺寸种子空间做周期探针。
- 固定视觉图集，测量像素变化率、相邻相关性和边缘相似度。
- 完成人工视觉初审后冻结阈值和发布日期。

---

## 附录 A：面向读者的算法讲解

上面 1–5 节是给验证者看的严格规范。这一节是给"想弄明白 V1 到底在做什么"的读者看的说明；所有公式都用等价的 Python/C 风格写法给出，方便对照 [reference_v1.py](../reversible_mosaic/core/algorithm/reference_v1.py) 逐行读。

### A.1 一句话概括

V1 是**逐像素、逐字节可逆的整数域"打码"变换**——把一张 8-bit RGB/RGBA 图像扰乱成人眼不可辨认的样子，凭"算法版本 + 轮数 + 分享代码"这三件套可以逐字节还原规范化像素矩阵。

它**不是加密**：算法开源，任何人都能穷举 100 亿个分享代码；它也不带 MAC，改一位密文再解密依然会解出一张"看起来是图"的东西。它只提供两件事：

- **可逆性**：给对参数就能一比特不差地还原
- **视觉扰乱**：肉眼看不出原图内容

需求档 §11.2 把这些非目标写得很清楚。

### A.2 输入与规范化

进入算法前，图片会被规范化成一个 numpy 矩阵：

```
I : uint8[H][W][C]     # C = 3 (RGB) 或 4 (RGBA)
```

JPEG 的 EXIF Orientation 1–8 会先应用一次，输出到算法前的所有像素都已经"摆正"了。算法看不到文件字节，也不关心 EXIF/ICC/文件名——它只吃这个矩阵。

### A.3 从"分享代码"到"轮密钥"

用户看到的**分享代码**是 1–10 位十进制数字（默认 `500000`）。去前导零后成为**扰动种子** `s ∈ [0, 9_999_999_999]`。

第一步：把种子和图片规格拼成一段 43 字节的确定性负载，做一次 SHA-256，切成 4 个 64-bit 主密钥字。

```
payload = "reversible_mosaic/algorithm/v1\0"      # 31 B 域分离标签
        || LE64(seed)                              # 8 B
        || LE32(width) || LE32(height)             # 8 B
        || LE32(1)                                 # 4 B  algorithm_version
        || LE8(mode_id)                            # 1 B  RGB=3, RGBA=4

(K0, K1, K2, K3) = split(SHA256(payload), 64bit x 4)   # 小端
```

**"域分离标签"**的作用：即使别的软件也用 SHA-256 派生参数，只要不带这串固定字节，就一定得到不同的密钥。种子改一位、宽高改一像素、RGB↔RGBA 切换——四个 K_i 全变。

第二步：每一轮 r（r = 0, 1, ..., n-1）用 SplitMix64 快速 PRF 派生四个子密钥：

```
tau = [0x11, 0x22, 0x33, 0x44]      # 阶段标签，分开四路密钥流
k_r[i] = splitmix64( K_i XOR (r * 0xD1342543DE82EF95) XOR tau[i] )
```

SplitMix64 本身是三步 64-bit 整数混合（Guy L. Steele Jr. et al. 2014），不是密码学 PRF，但雪崩性够好、速度极快。作用就是"给定一个整数索引，喷一段确定性的伪随机字节"。

### A.4 单轮变换：四个阶段

把矩阵铺平成 N = H*W 个"像素行"：

```
flat = I.reshape(N, C)
```

单轮的正向变换由四段构成，**顺序固定**：

```
lift  →  permute  →  diffuse_forward  →  diffuse_reverse
```

每一段都是"确定性双射"（同一输入永远得到同一输出，且能逆回去）。逆变换按相反顺序、每段各自的逆步骤执行。

#### A.4.1 三角 lifting（RGB 通道混合）

对每个像素 (r, g, b)（Alpha 完全不读、不写），先用像素索引派生 3 字节掩码：

```
w = splitmix64(key XOR index)
m0 = w & 0xFF
m1 = (w >> 8) & 0xFF
m2 = (w >> 16) & 0xFF
```

正向变换（注意每一步用的是**刚刚更新后**的值）：

```
r' = (r  + 3*g  + 5*b  + m0) & 0xFF
g' = (g  + 5*b  + 7*r' + m1) & 0xFF
b' = (b  + 7*r' + 3*g' + m2) & 0xFF
```

逆变换按**相反顺序**减回来：

```
b = (b' - 7*r' - 3*g' - m2) & 0xFF
g = (g' - 5*b  - 7*r' - m1) & 0xFF
r = (r' - 3*g  - 5*b  - m0) & 0xFF
```

**为什么可逆**：这是密码学里经典的"三角提升"（triangular lifting）。每一步只把新值定义为"当前通道 + 已知的其他通道的线性组合 + 掩码"，对应的变换矩阵在 mod 256 下是**单位下三角**（对角线全 1）：

```
| 1  0  0 |   | r + 3g + 5b + m0 |
| 7  1  0 | * | g + 5b      + m1 |
| 7  3  1 |   | b           + m2 |
```

单位下三角矩阵在任意交换环上都可逆（行列式恒等于 1）。即使 8-bit 通道有环形溢出，减法也能完整还原。

**Alpha 通道**：不读、不写。透明像素（α=0）里那些"看不见但存在"的 RGB 值（比如 `[200, 100, 50, 0]`）完全保留。

#### A.4.2 Fisher–Yates 置换（把像素搬位置）

把 N 个像素**整体**（RGB 或 RGBA 四通道一起）打乱到新位置。用可随机访问的 Fisher–Yates：

正向（i 从 N-1 递减到 1）：

```
for i = N-1 down to 1:
    w = splitmix64(key XOR i)
    j = (w * (i + 1)) >> 64      # 无偏乘法映射到 [0, i]
    swap(flat[i], flat[j])
```

其中 `(w * (i+1)) >> 64` 是 **Lemire 2019 无偏映射**——比传统 `w % (i+1)` 少了模偏差。

逆向（i 从 1 递增到 N-1）：**用相同 PRF 重新算出每个 j，再逐个 swap**。

```
for i = 1 to N-1:
    w = splitmix64(key XOR i)
    j = (w * (i + 1)) >> 64
    swap(flat[i], flat[j])
```

**为什么可逆而且不需要保存置换表**：

- Fisher–Yates 每一步都是"两个位置的对换"，对换是自逆的：`(i,j) ∘ (i,j) = 恒等`
- 正向按 `i = N-1, N-2, ..., 1` 顺序做换位；逆向按**相反顺序** `i = 1, 2, ..., N-1` 做**同一批**换位——效果完全对消
- j 由 PRF 从 `(key, i)` 完全确定，正向逆向能重现相同索引

**RGBA**：四通道**共同移动**（swap 时整个像素行一起换），所以 Alpha 数值不会被单独打乱到别的位置。

#### A.4.3 反馈链扩散（正向 + 反向各一次）

Lifting 只是"每个像素独立地混色"，permute 只是"搬位置"，两者都没有让**位置相邻的像素**互相污染。扩散阶段负责这件事。

只处理 RGB 三通道（Alpha 依然不动）。用一条反馈链：

正向扫描（index 从 0 到 N-1）：

```
prev = mask3(key, 0xFFFFFFFFFFFFFFFF)     # 从 IV 起头
for i = 0 to N-1:
    (m0, m1, m2) = mask3(key, i)
    src = flat[i, 0..2]
    out[0] = (src[0] + prev[1] + m0) & 0xFF    # R 依赖上一像素的 G
    out[1] = (src[1] + prev[2] + m1) & 0xFF    # G 依赖上一像素的 B
    out[2] = (src[2] + prev[0] + m2) & 0xFF    # B 依赖上一像素的 R
    flat[i, 0..2] = out
    prev = out
```

注意"通道错位"—— R 依赖上一像素的 G，G 依赖上一像素的 B，B 依赖上一像素的 R——这让相邻像素之间**跨通道**互相污染。

逆向变换（相同扫描方向）：

```
prev = mask3(key, 0xFFFFFFFFFFFFFFFF)
for i = 0 to N-1:
    (m0, m1, m2) = mask3(key, i)
    encoded = flat[i, 0..2]             # 这是正向写入的 out
    flat[i, 0] = (encoded[0] - prev[1] - m0) & 0xFF
    flat[i, 1] = (encoded[1] - prev[2] - m1) & 0xFF
    flat[i, 2] = (encoded[2] - prev[0] - m2) & 0xFF
    prev = encoded                      # 关键：用 encoded 而不是解出的原值
```

**关键**：正向时 `prev = out`（新写入的值），逆向时 `prev = encoded`（读到的值）——因为逆向在读到 `encoded` 时，那个 `encoded` 就是正向写入的 `out`。这样两条链条对齐，减法能完整还原。

**为什么正向 + 反向各来一次**：

- 单次正向：像素 i 只受到 `i-1, i-2, ..., 0` 的影响；最左边的像素只吃 IV
- 单次反向：像素 i 只受到 `i+1, i+2, ..., N-1` 的影响
- 两次合起来：任何像素的最终值都受**整幅图所有像素**的影响——1 bit 输入差异能雪崩到 O(N) bit 输出

这是可逆混淆的核心手段。

### A.5 多轮：为什么允许 1 / 5 / 10 / 20？

单轮变换里的三次扩散只在一维顺序上传播。视觉上一轮通常不够扰乱：图片的宏观结构（边、色块、人脸轮廓）会残存。

多轮就是把单轮迭代 n 次，每一轮的子密钥都不同（r 参与派生），所以不是简单的幂次：

```
F_n(I) = F_{n-1}(F_{n-2}(...(F_1(F_0(I))))
```

- **1 轮**：主要做数学 sanity check（能被正确还原），视觉扰乱可能不足
- **5 轮**：MVP 默认，兼顾速度与视觉扰乱
- **10 轮**：中等强度
- **20 轮**：最大扰乱

需求 §12.3.6 要求做冻结前视觉验收：如果同一分享代码在 3 张以上"内容丰富的测试图"上没通过阈值，就视为参数派生规则有系统性退化，该 V1 不得发布。

### A.6 解码：反着来

解码是"每一轮各自求逆，然后按 r = n-1, n-2, ..., 0 反顺序应用"：

```
G_n(C) = F_0^-1(F_1^-1(...(F_{n-2}^-1(F_{n-1}^-1(C))))
```

单轮的逆是四段各自求逆，也按反顺序：

```
F_r^-1 = lift_inv  ∘  permute_inv  ∘  diffuse_fwd_inv  ∘  diffuse_rev_inv
```

严格的"每一步都可逆 + 反顺序执行"是需求档 §5.2 的硬性要求。

### A.7 Alpha 通道的三条约定

需求档 §5.7 / §5.8 / §7.3.9：

1. **Alpha 数值不被读、不被修改、不被与 RGB 混合**——所以 lifting 和 diffusion 只操作前 3 通道
2. **Alpha 随空间置换共同移动**——permute 阶段整个像素行一起 swap
3. **透明像素（α=0）中的 RGB 必须保留**——不能因为"看不见"就清零，否则不可逆

代码上体现在：`_lift_forward` / `_lift_inverse` / `_diffuse_forward` / `_diffuse_inverse` 都只对 `pixel[0..2]` 或 `flat[index, :3]` 操作，不碰 `pixel[3]`；permute 是整行 swap。

正确参数下，RGBA 图的每个通道（包括 α=0 像素的 RGB）都逐字节还原。自检屏的第四个探针就是在真机上验证这件事。

### A.8 可逆性的直觉证明

**命题**：对任意合法的 (version, seed, rounds, I)，`decrypt(encrypt(I)) == I`（逐字节相等）。

**为什么成立**：

1. **lift** 是 mod 256 下的单位下三角变换，行列式恒为 1，所以在 Z/256Z 上是双射
2. **permute** 是 N-1 个基本对换的复合；置换群 S_N 是群，任何元素都有逆；逆变换用相同 PRF 从相反方向重放对换正好抵消
3. **diffuse** 的反馈链 `y_i = (x_i + f(y_{i-1}) + m_i) mod 256`，给定 `y_{i-1}` 时对 x_i 是双射；解码时从相同方向读 y_i，用**读到的 y_i** 当下一步的 prev（而不是解出的 x_i），链条对齐
4. 单轮 = 四个双射的复合 = 双射
5. 多轮 = n 个双射的复合 = 双射

"逐字节相等"是需求档 AC-008 的最硬指标，`tests/property/` 和 `tests/vectors/` 都在覆盖它。

### A.9 边缘尺寸的处理

需求 §5.9 要求"边缘和小尺寸必须采用可逆规则，不得裁剪或以补值替代原像素"。

看代码：`_diffuse_forward` 用 `range(len(flat))` 或 `range(len(flat)-1, -1, -1)`——从 index 0 或 N-1 开始，每次的 `prev` 初值都是**密钥派生的 IV**，不需要越界访问相邻像素。所以：

- **1×1**：只有一个像素，diffusion 变成 `out = src + IV + mask`，减回来一样成立
- **1×N、N×1**：一维序列，链条不断
- **奇数尺寸**：无特殊分支
- **全透明**（Alpha=0）：RGB 依然被 lifting + diffusion 打乱，Alpha 单独 permute 走位置

这些 corner case 在 `tests/unit/test_algorithm_v1.py` 和 `tests/property/test_algorithm_properties.py` 里都有覆盖。

### A.10 冻结常量清单

到 V1 冻结日为止，以下常量**永远不能改**（改了必须叫 V2）：

| 名字 | 值 | 出处 |
|---|---|---|
| 域分离标签 | `"reversible_mosaic/algorithm/v1\0"` | `_derive_words` |
| SplitMix64 加常数 | `0x9E3779B97F4A7C15` | `_splitmix64` |
| SplitMix64 乘常数 A | `0xBF58476D1CE4E5B9` | `_splitmix64` |
| SplitMix64 乘常数 B | `0x94D049BB133111EB` | `_splitmix64` |
| 轮索引乘子 | `0xD1342543DE82EF95` | `_round_key` |
| 阶段标签 | `0x11 / 0x22 / 0x33 / 0x44` | `encrypt`/`decrypt` |
| Lift 矩阵系数 | `3, 5, 7` | `_lift_forward` |
| Diffusion IV 索引 | `0xFFFFFFFFFFFFFFFF` | `_diffuse_forward` |
| Diffusion 通道错位 | `(c + 1) mod 3` | `_diffuse_forward` |
| 单轮阶段顺序 | `lift → permute → diffuse_fwd → diffuse_rev` | `encrypt` |
| 分享代码上限 | `9_999_999_999`（10 位十进制） | `_derive_words` |
| 允许轮数 | `{1, 5, 10, 20}` | `VALID_ROUNDS` |

冻结锚点在 `tests/vectors/vectors.json`（PC 生成一次、跨平台 diff）。任何一处改动都会让 `test_v1_vectors.py` 立刻变红。

### A.11 非目标（重申）

1. **不是加密**：源码开源 + 分享代码空间只有 10^10，任何人都能穷举
2. **不隐藏元数据**：PNG tEXt 里明文写 `algorithm_version` / `rounds` / `pixel_mode`（但**绝不写 seed**）
3. **抗篡改能力 = 0**：不带 MAC，改一位密文也能"解密"，只是得到错的
4. **社交平台重压缩不保**：微信 / 微博 / QQ 空间会重编 JPEG → 像素被有损 → 解密出乱码
5. **不用 Python `hash()`**：CPython 的 `hash(str)` 加了 PYTHONHASHSEED 随机化，跨进程不可复现；V1 全用 SHA-256 + SplitMix64，跨设备位一致

### A.12 性能画像

| 层 | 实现 | 当前状态 |
|---|---|---|
| 规范代表 | [reference_v1.py](../reversible_mosaic/core/algorithm/reference_v1.py) 纯 Python | 慢，作为跨平台 oracle |
| 优化候选 | `v1.pyx` Cython（`nogil` 释放 GIL） | 阶段 1 已接入生产（`optimized_v1.py` + `registry.py` fallback） |
| Pipeline 集成 | **阶段 1 v7 完成** | `registry.get(1)` 优先返回 Cython 后端；PC/CI 无 Cython 时自动退回 reference |

阶段 1 真机基准（1920×1080 RGB, 5 次中位数, v7 APK, `registry V1 backend = cython`, 2026-07-28）：

| 轮数 | 实测 median | 实测 p95 | AC-PERF 上限 | 余量 |
|---|---|---|---|---|
|  1 | 0.060 s | 0.062 s |  3.0 s | 50× |
|  5 | 0.268 s | 0.368 s |  ~9.0 s | 34× |
| 10 | 0.543 s | 0.611 s | 18.0 s | 33× |
| 20 | 1.072 s | 1.133 s | 35.0 s | 33× |

峰值 RSS 274.7 MiB（覆盖 3 份 1920×1080×3=18.6 MiB 全分辨率缓冲 + 64 MiB 固定开销 + Kivy 运行时）。
测试机型/SoC 及冷/热状态尚未记入本报告，正式发布前需在 [docs/probe-report.md](probe-report.md) 补齐。
