"""Generate synthetic + adversarial test samples for §12.1-12.2 / §12.4.

Emits three folders under ``artifacts/synthetic_test_set/``:

- ``rgba/``   — 8 valid RGBA PNGs covering Alpha edge cases (all-opaque,
                all-transparent-non-zero-RGB, half-transparent gradient, sparse
                holes, random, ...).
- ``boundary/`` — 8 valid images covering size / aspect / content extremes
                  (1x1, 1xN, Nx1, odd dims, solid colour, pure noise, extreme
                  aspect ratio, near-limit pixel count).
- ``adversarial/`` — 10 malformed files that MUST be rejected by
                     ``io.probe.scan_png`` / ``io.normalize.normalize_image``
                     (truncated / bogus dims / bad CRC / zero-byte / random
                     bytes with image-file extension / bogus EXIF Orientation).

All outputs are deterministic (fixed RNG seed). A ``manifest.csv`` in each
folder records ``filename, sha256, category, notes``.

Run once with::

    python scripts/generate_synthetic_test_set.py
"""

# ruff: noqa: RUF001  -- Chinese notes contain fullwidth punctuation on purpose.
from __future__ import annotations

import csv
import hashlib
import io
import struct
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "artifacts" / "synthetic_test_set"

_SEED = 20260729  # fixed so re-runs produce byte-identical files


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 16), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Valid RGBA samples
# ---------------------------------------------------------------------------


def _gen_rgba(root: Path, rng: np.random.Generator) -> list[tuple[str, str]]:
    root.mkdir(parents=True, exist_ok=True)
    records: list[tuple[str, str]] = []

    # 1. Fully opaque gradient
    grad = np.zeros((128, 128, 4), dtype=np.uint8)
    grad[..., 0] = np.linspace(0, 255, 128, dtype=np.uint8)[None, :]
    grad[..., 1] = np.linspace(0, 255, 128, dtype=np.uint8)[:, None]
    grad[..., 2] = 128
    grad[..., 3] = 255
    _save(root / "rgba_all_opaque_gradient.png", grad, records, "全不透明 128x128 RGB 梯度")

    # 2. All fully transparent (Alpha=0) with non-zero RGB — the critical case
    #    for §5.8 "透明像素中的 RGB 必须保留"
    transparent = np.zeros((64, 64, 4), dtype=np.uint8)
    transparent[..., 0] = rng.integers(0, 256, size=(64, 64), dtype=np.uint8)
    transparent[..., 1] = rng.integers(0, 256, size=(64, 64), dtype=np.uint8)
    transparent[..., 2] = rng.integers(0, 256, size=(64, 64), dtype=np.uint8)
    transparent[..., 3] = 0
    _save(
        root / "rgba_all_transparent_hidden_rgb.png",
        transparent,
        records,
        "Alpha=0 但 RGB 非零；核心可逆性回归样本",
    )

    # 3. Alpha diagonal gradient over solid red
    diag = np.zeros((96, 96, 4), dtype=np.uint8)
    diag[..., 0] = 220
    diag[..., 1] = 30
    diag[..., 2] = 40
    coords_y, coords_x = np.meshgrid(np.arange(96), np.arange(96), indexing="ij")
    diag[..., 3] = np.clip((coords_x + coords_y) * (255 / 190), 0, 255).astype(np.uint8)
    _save(root / "rgba_diagonal_alpha_gradient.png", diag, records, "对角 Alpha 渐变 + 纯红 RGB")

    # 4. Sparse transparent holes on solid green
    sparse = np.zeros((128, 128, 4), dtype=np.uint8)
    sparse[..., 1] = 200
    sparse[..., 3] = 255
    holes = rng.integers(0, 128, size=(30, 2))
    for y, x in holes:
        sparse[y : y + 4, x : x + 4, 3] = 0
        sparse[y : y + 4, x : x + 4, 0] = 180  # non-zero RGB under transparent holes
    _save(root / "rgba_sparse_transparent_holes.png", sparse, records, "散落 Alpha=0 洞，RGB≠0")

    # 5. Fully random RGBA
    fully_random = rng.integers(0, 256, size=(128, 128, 4), dtype=np.uint8)
    _save(root / "rgba_random_noise.png", fully_random, records, "所有通道全随机")

    # 6. Uniform half-alpha
    half = np.zeros((80, 80, 4), dtype=np.uint8)
    half[..., 0] = np.linspace(0, 255, 80, dtype=np.uint8)[None, :]
    half[..., 1] = np.linspace(0, 255, 80, dtype=np.uint8)[:, None]
    half[..., 2] = 64
    half[..., 3] = 128
    _save(root / "rgba_uniform_half_alpha.png", half, records, "所有像素 Alpha=128")

    # 7. Simulated rounded-corner button (anti-aliased Alpha)
    button_img = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(button_img)
    draw.rounded_rectangle((4, 4, 196, 76), radius=20, fill=(30, 140, 240, 235))
    draw.text((60, 26), "OK", fill=(255, 255, 255, 255))
    button = np.array(button_img, dtype=np.uint8)
    _save(root / "rgba_ui_button.png", button, records, "圆角按钮，反锯齿 Alpha")

    # 8. RGBA with Alpha=255 everywhere but heavy RGB texture
    texture = rng.integers(0, 256, size=(96, 128, 3), dtype=np.uint8)
    solid_alpha = np.concatenate(
        [texture, np.full((96, 128, 1), 255, dtype=np.uint8)], axis=2
    )
    _save(root / "rgba_solid_alpha_random_rgb.png", solid_alpha, records, "Alpha 全 255，RGB 随机")

    return records


# ---------------------------------------------------------------------------
# Valid boundary samples
# ---------------------------------------------------------------------------


def _gen_boundary(root: Path, rng: np.random.Generator) -> list[tuple[str, str]]:
    root.mkdir(parents=True, exist_ok=True)
    records: list[tuple[str, str]] = []

    # 1. 1x1 RGB
    _save(
        root / "boundary_1x1_rgb.png",
        np.array([[[200, 30, 40]]], dtype=np.uint8),
        records,
        "单像素 RGB",
    )

    # 2. 1x1 RGBA with Alpha=0
    _save(
        root / "boundary_1x1_rgba_hidden.png",
        np.array([[[123, 45, 67, 0]]], dtype=np.uint8),
        records,
        "单像素 RGBA，Alpha=0 但 RGB≠0",
    )

    # 3. 1 x 64 narrow column (RGB gradient) — at MAX_ASPECT_RATIO 64:1 cap
    column = np.zeros((64, 1, 3), dtype=np.uint8)
    column[:, 0, 0] = np.linspace(0, 255, 64, dtype=np.uint8)
    _save(root / "boundary_1x64_narrow_column.png", column, records, "1 列 x 64 行 RGB (64:1)")

    # 4. 64 x 1 narrow row — same but rotated
    row = np.zeros((1, 64, 3), dtype=np.uint8)
    row[0, :, 1] = np.linspace(0, 255, 64, dtype=np.uint8)
    _save(root / "boundary_64x1_narrow_row.png", row, records, "64 列 x 1 行 RGB (64:1)")

    # 5. Odd 17x23 dimensions
    odd = rng.integers(0, 256, size=(23, 17, 3), dtype=np.uint8)
    _save(root / "boundary_17x23_odd.png", odd, records, "奇数宽 17 x 高 23")

    # 6. Solid black RGB
    solid = np.zeros((128, 128, 3), dtype=np.uint8)
    _save(root / "boundary_solid_black_128x128.png", solid, records, "纯黑，低信息")

    # 7. Pure white noise 256x256 RGB
    noise = rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)
    _save(root / "boundary_pure_noise_256x256.png", noise, records, "全随机噪声")

    # 8. Extreme aspect ratio 64:1 (640x10) — at MAX_ASPECT_RATIO cap
    strip = np.zeros((10, 640, 3), dtype=np.uint8)
    strip[..., 2] = np.linspace(0, 255, 640, dtype=np.uint8)[None, :]
    _save(root / "boundary_extreme_aspect_640x10.png", strip, records, "宽高比 64:1 恰在上限")

    return records


# ---------------------------------------------------------------------------
# Adversarial samples (MUST be rejected)
# ---------------------------------------------------------------------------


def _write_png_chunk(
    stream: io.BytesIO, chunk_type: bytes, data: bytes, *, override_crc: int | None = None
) -> None:
    stream.write(struct.pack(">I", len(data)))
    stream.write(chunk_type)
    stream.write(data)
    crc = override_crc if override_crc is not None else zlib.crc32(chunk_type + data)
    stream.write(struct.pack(">I", crc & 0xFFFFFFFF))


def _gen_adversarial(root: Path, rng: np.random.Generator) -> list[tuple[str, str]]:
    root.mkdir(parents=True, exist_ok=True)
    records: list[tuple[str, str]] = []
    png_sig = b"\x89PNG\r\n\x1a\n"

    # 1. Zero bytes
    (root / "adv_zero_bytes.png").write_bytes(b"")
    records.append(("adv_zero_bytes.png", "空文件"))

    # 2. Random bytes with .png extension
    random_bytes = rng.integers(0, 256, size=512, dtype=np.uint8).tobytes()
    (root / "adv_random_bytes.png").write_bytes(random_bytes)
    records.append(("adv_random_bytes.png", ".png 后缀但内容是随机字节"))

    # 3. Random bytes with .jpg extension
    (root / "adv_random_bytes.jpg").write_bytes(random_bytes)
    records.append(("adv_random_bytes.jpg", ".jpg 后缀但内容是随机字节"))

    # 4. Truncated PNG (signature + IHDR only, no IDAT/IEND)
    stream = io.BytesIO()
    stream.write(png_sig)
    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)  # 8x8 RGB 8-bit
    _write_png_chunk(stream, b"IHDR", ihdr)
    (root / "adv_truncated_png.png").write_bytes(stream.getvalue())
    records.append(("adv_truncated_png.png", "PNG 头 + IHDR 后立刻截断"))

    # 5. PNG with intentionally wrong IHDR CRC
    stream = io.BytesIO()
    stream.write(png_sig)
    _write_png_chunk(stream, b"IHDR", ihdr, override_crc=0xDEADBEEF)
    # Add a valid IEND so the chunk walker reaches IHDR before failing.
    _write_png_chunk(stream, b"IEND", b"")
    (root / "adv_bad_crc_ihdr.png").write_bytes(stream.getvalue())
    records.append(("adv_bad_crc_ihdr.png", "IHDR CRC 错误"))

    # 6. PNG declaring absurd dimensions in IHDR
    stream = io.BytesIO()
    stream.write(png_sig)
    absurd = struct.pack(">IIBBBBB", 200_000, 200_000, 8, 2, 0, 0, 0)
    _write_png_chunk(stream, b"IHDR", absurd)
    _write_png_chunk(stream, b"IEND", b"")
    (root / "adv_bogus_dimensions.png").write_bytes(stream.getvalue())
    records.append(("adv_bogus_dimensions.png", "IHDR 声称 200000x200000"))

    # 7. Truncated JPEG (SOI + APP0 header, then cut)
    truncated_jpeg = bytes.fromhex("ffd8ffe000104a46494600010100000100010000")
    (root / "adv_truncated_jpeg.jpg").write_bytes(truncated_jpeg)
    records.append(("adv_truncated_jpeg.jpg", "JPEG SOI + APP0 立刻截断"))

    # 8. Not-a-JPEG file with .jpeg extension (magic bytes wrong)
    (root / "adv_not_a_jpeg.jpeg").write_bytes(b"THIS IS NOT AN IMAGE" + b"\x00" * 200)
    records.append(("adv_not_a_jpeg.jpeg", ".jpeg 但没有 JPEG 头"))

    # 9. JPEG with bogus EXIF Orientation value (spec allows 1-8; we inject 42).
    #    Build a proper APP1 EXIF segment with TIFF IFD holding Orientation=42.
    base = io.BytesIO()
    Image.new("RGB", (16, 16), (100, 100, 100)).save(base, format="JPEG", quality=90)
    base_bytes = base.getvalue()
    # Construct minimal TIFF (little-endian) with one IFD entry: Orientation (0x0112).
    tiff = b"II*\x00" + struct.pack("<I", 8)  # header + offset to first IFD
    tiff += struct.pack("<H", 1)  # 1 entry
    tiff += struct.pack("<HHII", 0x0112, 3, 1, 42)  # tag=Orientation, type=SHORT, count=1, value=42
    tiff += struct.pack("<I", 0)  # next IFD offset = 0 (none)
    exif_payload = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload
    # Insert APP1 right after SOI (\xff\xd8).
    injected = base_bytes[:2] + app1 + base_bytes[2:]
    (root / "adv_bogus_exif_orientation.jpg").write_bytes(injected)
    records.append(("adv_bogus_exif_orientation.jpg", "APP1 EXIF Orientation=42 (spec 允许 1-8)"))

    # 10. PNG with extra data after IEND (chunk walker should stop cleanly at IEND;
    #     this checks it does not misread the trailing bytes as another chunk)
    stream = io.BytesIO()
    stream.write(png_sig)
    # Build a minimal but valid 1x1 RGB PNG
    ihdr_1x1 = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    _write_png_chunk(stream, b"IHDR", ihdr_1x1)
    idat_payload = zlib.compress(b"\x00\x11\x22\x33")  # filter=0 + 1 RGB pixel
    _write_png_chunk(stream, b"IDAT", idat_payload)
    _write_png_chunk(stream, b"IEND", b"")
    stream.write(b"POST-IEND JUNK BYTES SHOULD BE IGNORED OR CAUSE REJECT")
    (root / "adv_trailing_garbage_after_iend.png").write_bytes(stream.getvalue())
    records.append(
        ("adv_trailing_garbage_after_iend.png", "IEND 后附加垃圾字节 — 边界样本")
    )

    return records


# ---------------------------------------------------------------------------


def _save(
    path: Path,
    pixels: np.ndarray,
    records: list[tuple[str, str]],
    note: str,
) -> None:
    mode = "RGB" if pixels.shape[2] == 3 else "RGBA"
    Image.fromarray(pixels, mode=mode).save(path, format="PNG", optimize=False)
    records.append((path.name, note))


def _write_manifest(folder: Path, records: list[tuple[str, str]]) -> None:
    manifest = folder / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["filename", "sha256", "category", "notes", "license"])
        category = folder.name
        for name, note in records:
            path = folder / name
            digest = _sha256(path) if path.exists() else ""
            writer.writerow([name, digest, category, note, "本项目 CC0"])


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(_SEED)

    for folder_name, generator in [
        ("rgba", _gen_rgba),
        ("boundary", _gen_boundary),
        ("adversarial", _gen_adversarial),
    ]:
        folder = OUTPUT_ROOT / folder_name
        records = generator(folder, rng)
        _write_manifest(folder, records)
        print(f"[{folder_name}] wrote {len(records)} files -> {folder}")

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
