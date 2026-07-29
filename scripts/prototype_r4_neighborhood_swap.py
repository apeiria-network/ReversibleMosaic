"""Prototype: R=4 constant, per-pixel neighborhood swap + lift, no diffuse.

This is a THROWAWAY test to visually confirm the new V1 curve before doing
the full reference_v1.py + v1.pyx rewrite. Uses the same lift as current
V1 (frozen for now) plus a new self-inverse neighborhood_swap.

Output: artifacts/prototype/<pid>_R04_r{01,05,10,20}.png plus a side-by-side
mosaic ``artifacts/prototype/<pid>_compare.png`` so the reviewer can eyeball
1/5/10/20-round outputs against the source in one image.

Do not import this module from production code.

Run::

    python scripts/prototype_r4_neighborhood_swap.py --image p5 --pid p5
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from reversible_mosaic.io.normalize import normalize_image

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = REPO_ROOT / "artifacts" / "visual_review_sources"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "prototype"

RADIUS_MIN = 8         # floor for very small images
RADIUS_DIVISOR = 16    # min-dim / divisor gives adaptive radius above the floor
DEFAULT_DENSITY = 1.00 # fraction of pixels selected per pass
PASSES_PER_ROUND = 1   # how many independent swap passes per user-facing round
COLOR_K = 0            # per-pass color shift amplitude, 0 = color transform disabled
DEFAULT_SEED = 500_000                                  # -> 1 pass x 100% = 100% total density


def _radius_for(width: int, height: int) -> int:
    """Adaptive radius: R = max(8, min(W, H) // 16)."""
    return max(RADIUS_MIN, min(width, height) // RADIUS_DIVISOR)


def _density_threshold(density: float) -> int:
    """Return the low-byte cutoff s.t. ``prf & 0xFF < cutoff`` fires with prob=density."""
    return max(0, min(256, int(round(density * 256))))

_MASK64 = (1 << 64) - 1
_DOMAIN = b"reversible_mosaic/algorithm/v1\x00"


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & _MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
    return (value ^ (value >> 31)) & _MASK64


def _derive_words(width: int, height: int, mode_id: int, seed: int) -> tuple[int, ...]:
    payload = _DOMAIN + struct.pack("<QIIIB", seed, width, height, 1, mode_id)
    return struct.unpack("<QQQQ", hashlib.sha256(payload).digest())


def _round_key(word: int, round_index: int, domain: int) -> int:
    return _splitmix64(word ^ (round_index * 0xD1342543DE82EF95) ^ domain)


def _mask3(key: int, index: int) -> tuple[int, int, int]:
    value = _splitmix64(key ^ index)
    return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF


def _lift_forward_2d(pixels: np.ndarray, key: int) -> None:
    height, width, _ = pixels.shape
    for y in range(height):
        for x in range(width):
            index = y * width + x
            m0, m1, m2 = _mask3(key, index)
            r, g, b = int(pixels[y, x, 0]), int(pixels[y, x, 1]), int(pixels[y, x, 2])
            r = (r + 3 * g + 5 * b + m0) & 0xFF
            g = (g + 5 * b + 7 * r + m1) & 0xFF
            b = (b + 7 * r + 3 * g + m2) & 0xFF
            pixels[y, x, 0] = r
            pixels[y, x, 1] = g
            pixels[y, x, 2] = b


def _lift_inverse_2d(pixels: np.ndarray, key: int) -> None:
    height, width, _ = pixels.shape
    for y in range(height):
        for x in range(width):
            index = y * width + x
            m0, m1, m2 = _mask3(key, index)
            r, g, b = int(pixels[y, x, 0]), int(pixels[y, x, 1]), int(pixels[y, x, 2])
            b = (b - 7 * r - 3 * g - m2) & 0xFF
            g = (g - 5 * b - 7 * r - m1) & 0xFF
            r = (r - 3 * g - 5 * b - m0) & 0xFF
            pixels[y, x, 0] = r
            pixels[y, x, 1] = g
            pixels[y, x, 2] = b


_U64_MOD = np.uint64(1 << 63) * np.uint64(2)  # 2^64, for wrap-around arithmetic


def _splitmix64_vec(x: np.ndarray) -> np.ndarray:
    """Vectorised SplitMix64 finalizer on uint64 arrays."""
    C1 = np.uint64(0x9E3779B97F4A7C15)
    C2 = np.uint64(0xBF58476D1CE4E5B9)
    C3 = np.uint64(0x94D049BB133111EB)
    x = (x + C1)
    x = (x ^ (x >> np.uint64(30))) * C2
    x = (x ^ (x >> np.uint64(27))) * C3
    return x ^ (x >> np.uint64(31))


def _precompute_j_targets_and_mask(
    key: int, radius: int, width: int, height: int, density: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return (partner-index array, boolean chosen mask) for length H*W.

    ``chosen[i]`` decides whether pixel ``i`` participates in the swap this
    round. Use two independent domain-separated PRFs so that the (dy, dx)
    offset and the "am I chosen?" test do not share bits.
    """
    n = width * height
    denom = np.uint64(2 * radius + 1)
    W_u = np.uint64(width)
    H_u = np.uint64(height)
    R_u = np.uint64(radius)
    key_u = np.uint64(key)
    chosen_key = np.uint64(key ^ 0xC0DEF00DBADCAFEB) & np.uint64((1 << 64) - 1)

    indices = np.arange(n, dtype=np.uint64)
    offsets = _splitmix64_vec(key_u ^ indices)
    dy_u = (offsets >> np.uint64(32)) % denom
    dx_u = (offsets & np.uint64(0xFFFFFFFF)) % denom
    y = indices // W_u
    x = indices % W_u
    yj = (y + dy_u + H_u - R_u) % H_u
    xj = (x + dx_u + W_u - R_u) % W_u
    j_targets = (yj * W_u + xj).astype(np.uint64)

    # Independent PRF for the chosen mask so 100%-density remains a strict
    # superset of 25%-density swaps.
    chosen_prf = _splitmix64_vec(chosen_key ^ indices)
    threshold = np.uint64(_density_threshold(density))
    chosen = (chosen_prf & np.uint64(0xFF)) < threshold
    return j_targets, chosen


def _neighborhood_swap_forward_fast(
    pixels: np.ndarray, key: int, radius: int, density: float = DEFAULT_DENSITY
) -> None:
    """Forward pass: iterate i=0..N-1, swap when chosen[i] and j>i."""
    height, width, _ = pixels.shape
    n = height * width
    j_targets, chosen = _precompute_j_targets_and_mask(
        key, radius, width, height, density
    )
    flat = pixels.reshape(n, -1)
    for i in range(n):
        if not chosen[i]:
            continue
        j = int(j_targets[i])
        if j > i:
            tmp = flat[i].copy()
            flat[i] = flat[j]
            flat[j] = tmp


def _neighborhood_swap_inverse_fast(
    pixels: np.ndarray, key: int, radius: int, density: float = DEFAULT_DENSITY
) -> None:
    height, width, _ = pixels.shape
    n = height * width
    j_targets, chosen = _precompute_j_targets_and_mask(
        key, radius, width, height, density
    )
    flat = pixels.reshape(n, -1)
    for i in range(n - 1, -1, -1):
        if not chosen[i]:
            continue
        j = int(j_targets[i])
        if j > i:
            tmp = flat[i].copy()
            flat[i] = flat[j]
            flat[j] = tmp


def _neighborhood_swap_forward(pixels: np.ndarray, key: int, radius: int) -> None:
    """Fisher-Yates-style sparse local swap: iterate i = 0..N-1 forward.

    Each pixel i is independently chosen with probability ``DEFAULT_DENSITY``.
    Chosen pixels look up a partner index j via PRF constrained to the
    (2R+1)^2 window around i (modular wrap). Swap only when j > i so each
    unordered pair fires at most once from its lower-indexed member.
    """
    _neighborhood_swap_forward_fast(pixels, key, radius)


def _neighborhood_swap_inverse(pixels: np.ndarray, key: int, radius: int) -> None:
    """Undo the forward pass by walking indices in reverse."""
    _neighborhood_swap_inverse_fast(pixels, key, radius)


def _color_diffuse_forward(pixels: np.ndarray, key: int, k: int) -> None:
    """Bounded-amplitude reversible color diffusion chain.

    For each RGB channel independently, iterate ``i = 0..N-1``:
        prev = r[i-1, c] (encoded value) or IV for i=0
        delta = SplitMix64(key ^ i ^ prev) mod (2K+1) - K   ∈ [-K, +K]
        r[i, c] = (r[i, c] + delta) mod 256

    Adjacent pixels get correlated delta because they share the ``prev`` input,
    giving the "颜色蔓延 / 聚合" visual feel while keeping the modification
    strictly bounded by K per pass. Alpha channel is untouched (indices 0-2 only).
    """
    if k <= 0:
        return
    height, width, channels = pixels.shape
    n = height * width
    denom = 2 * k + 1
    flat = pixels.reshape(n, channels)
    for c in range(min(3, channels)):
        prev = int((key ^ (c * 0x11111)) & 0xFF)
        key_c = key ^ (c * 0x11111)
        for i in range(n):
            offset = _splitmix64(key_c ^ i ^ prev)
            delta = int(offset % denom) - k
            new_val = (int(flat[i, c]) + delta) & 0xFF
            flat[i, c] = new_val
            prev = new_val


def _color_diffuse_inverse(pixels: np.ndarray, key: int, k: int) -> None:
    """Undo :func:`_color_diffuse_forward` by walking indices in reverse.

    In reverse iteration ``i = N-1..0``, ``prev = flat[i-1, c]`` is still the
    encoded value (we have not touched it yet), so the same delta reproduces
    and we simply subtract instead of add.
    """
    if k <= 0:
        return
    height, width, channels = pixels.shape
    n = height * width
    denom = 2 * k + 1
    flat = pixels.reshape(n, channels)
    for c in range(min(3, channels)):
        iv = int((key ^ (c * 0x11111)) & 0xFF)
        key_c = key ^ (c * 0x11111)
        for i in range(n - 1, -1, -1):
            prev = int(flat[i - 1, c]) if i > 0 else iv
            offset = _splitmix64(key_c ^ i ^ prev)
            delta = int(offset % denom) - k
            new_val = (int(flat[i, c]) - delta) & 0xFF
            flat[i, c] = new_val


def encrypt_prototype(pixels: np.ndarray, seed: int, rounds: int) -> np.ndarray:
    """Position permutation + bounded color diffusion (both reversible).

    Each user-facing round runs ``PASSES_PER_ROUND`` passes; each pass does
    color_diffuse first (adjacent pixels get correlated ±K color shift) then
    neighborhood_swap. Different sub-keys per pass ensure diversity.
    """
    height, width, channels = pixels.shape
    mode_id = 3 if channels == 3 else 4
    words = _derive_words(width, height, mode_id, seed)
    radius = _radius_for(width, height)
    output = pixels.copy(order="C")
    for r in range(rounds):
        for pass_idx in range(PASSES_PER_ROUND):
            color_key = _round_key(words[0], r, 0x44 + pass_idx * 0x11)
            swap_key = _round_key(words[1], r, 0x22 + pass_idx * 0x11)
            _color_diffuse_forward(output, color_key, COLOR_K)
            _neighborhood_swap_forward(output, swap_key, radius)
    return output


def decrypt_prototype(pixels: np.ndarray, seed: int, rounds: int) -> np.ndarray:
    height, width, channels = pixels.shape
    mode_id = 3 if channels == 3 else 4
    words = _derive_words(width, height, mode_id, seed)
    radius = _radius_for(width, height)
    output = pixels.copy(order="C")
    for r in range(rounds - 1, -1, -1):
        for pass_idx in range(PASSES_PER_ROUND - 1, -1, -1):
            color_key = _round_key(words[0], r, 0x44 + pass_idx * 0x11)
            swap_key = _round_key(words[1], r, 0x22 + pass_idx * 0x11)
            _neighborhood_swap_inverse(output, swap_key, radius)
            _color_diffuse_inverse(output, color_key, COLOR_K)
    return output


def _side_by_side(source: np.ndarray, outputs: dict[int, np.ndarray]) -> np.ndarray:
    """Compose source + 4 outputs into a single 2x3 (or 3x2) mosaic."""
    rounds_list = sorted(outputs)
    all_imgs = [source] + [outputs[r] for r in rounds_list]
    h, w = source.shape[:2]
    channels = source.shape[2]
    # Scale down each to at most 400x400 for a manageable comparison canvas.
    scale = min(1.0, 400 / max(h, w))
    if scale < 1.0:
        new_h = int(h * scale)
        new_w = int(w * scale)
        scaled = []
        for img in all_imgs:
            mode = "RGBA" if img.shape[2] == 4 else "RGB"
            resized = Image.fromarray(img, mode=mode).resize((new_w, new_h), Image.NEAREST)
            scaled.append(np.array(resized))
        all_imgs = scaled
        h, w = new_h, new_w
    # Lay out 3 across, 2 rows.
    cols = 3
    rows = 2
    padding = 8
    canvas_h = rows * h + (rows + 1) * padding
    canvas_w = cols * w + (cols + 1) * padding
    if channels == 4:
        canvas = np.full((canvas_h, canvas_w, 4), 255, dtype=np.uint8)
    else:
        canvas = np.full((canvas_h, canvas_w, 3), 240, dtype=np.uint8)
    for idx, img in enumerate(all_imgs):
        row = idx // cols
        col = idx % cols
        y0 = padding + row * (h + padding)
        x0 = padding + col * (w + padding)
        canvas[y0 : y0 + h, x0 : x0 + w, :img.shape[2]] = img
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", default="p5", help="picture_id in sources.csv")
    parser.add_argument("--image", type=Path, help="path to specific image (overrides pid)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.image:
        source_path = args.image
        pid = source_path.stem
    else:
        candidates = [
            SOURCES_DIR / f"{args.pid}.jpg",
            SOURCES_DIR / f"{args.pid}.jpeg",
            SOURCES_DIR / f"{args.pid}.png",
        ]
        source_path = next((p for p in candidates if p.exists()), None)
        if source_path is None:
            print(f"ERROR: cannot find image for pid={args.pid}", file=sys.stderr)
            return 2
        pid = args.pid

    print(f"Source: {source_path}")
    normalized = normalize_image(source_path)
    source = normalized.pixels
    radius = _radius_for(source.shape[1], source.shape[0])
    print(f"  {source.shape[1]}x{source.shape[0]} {normalized.mode}  R={radius}")

    outputs: dict[int, np.ndarray] = {}
    for rounds in (2, 5, 10, 20):
        print(f"  encrypting rounds={rounds}...", flush=True)
        encrypted = encrypt_prototype(source, DEFAULT_SEED, rounds)
        outputs[rounds] = encrypted
        # Sanity: verify decrypt round-trips
        restored = decrypt_prototype(encrypted, DEFAULT_SEED, rounds)
        if not np.array_equal(restored, source):
            print(f"    !!! REVERSIBILITY FAILED at rounds={rounds}", file=sys.stderr)
            return 3
        # Save individual output
        mode = "RGBA" if source.shape[2] == 4 else "RGB"
        out_path = OUTPUT_DIR / f"{pid}_R{radius:03d}_r{rounds:02d}.png"
        Image.fromarray(encrypted, mode=mode).save(out_path)
        print(f"    saved {out_path.name}")

    print("Composing side-by-side comparison...")
    comparison = _side_by_side(source, outputs)
    mode = "RGBA" if comparison.shape[2] == 4 else "RGB"
    compare_path = OUTPUT_DIR / f"{pid}_compare.png"
    Image.fromarray(comparison, mode=mode).save(compare_path)
    print(f"  saved {compare_path}")
    print()
    print("Layout in compare image (2 rows x 3 cols):")
    print("  [source]  [r=1]   [r=5]")
    print("  [r=10]    [r=20]  [blank]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
