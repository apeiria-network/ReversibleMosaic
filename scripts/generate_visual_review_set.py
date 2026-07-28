"""Generate the pre-freeze visual review artefact bundle for V1.

Usage:

    python scripts/generate_visual_review_set.py \\
        --sources artifacts/visual_review_sources \\
        --output  artifacts/visual_review

For each image in ``--sources`` (RGB/RGBA PNG or plain RGB JPEG) the script:

1. Normalises the input (EXIF Orientation, mode conversion, resource limits).
2. Runs V1 encryption at rounds 1, 5, 10, 20 with a canonical seed set
   (``500_000`` and two secondary seeds so section 12.3.6 diverse-seed check
   has something to look at).
3. Saves each variant as an 8-bit RGB/RGBA PNG next to a JSON metrics file.
4. Aggregates all metrics into ``metrics.json`` and produces a printable
   ``scorecard.md`` that reviewers can use during the 3-person visual review
   (section 12.3.4 / 12.3.5).

The script is deterministic -- same sources + same seeds + same V1 registry
produces byte-identical outputs. It reads through ``core.pipeline`` on purpose
so it exercises the same path a real user hits.
"""

# ruff: noqa: RUF001  -- scorecard output uses fullwidth Chinese punctuation on purpose.
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reversible_mosaic.core.algorithm.quality import compute_metrics
from reversible_mosaic.core.algorithm.registry import get, v1_implementation
from reversible_mosaic.io.normalize import normalize_image, write_png
from reversible_mosaic.io.png_metadata import MosaicMetadata

CANONICAL_SEEDS: tuple[tuple[str, int], ...] = (
    ("default", 500_000),
    ("secondary_a", 314_159),
    ("secondary_b", 987_654_321),
)
ROUNDS: tuple[int, ...] = (1, 5, 10, 20)


@dataclass(frozen=True, slots=True)
class SourceRecord:
    identifier: str
    path: Path
    width: int
    height: int
    mode: str
    sha256: str


def _sha256_of_path(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _iter_source_images(sources: Path) -> list[Path]:
    matches: dict[Path, None] = {}
    for extension in ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"):
        for candidate in sources.glob(extension):
            matches.setdefault(candidate.resolve(), None)
    if not matches:
        raise SystemExit(
            f"未在 {sources} 找到可用的 PNG/JPEG。请把固定视觉图集放在这里再运行。"
        )
    return sorted(matches.keys())


def _load_source(path: Path) -> tuple[SourceRecord, np.ndarray]:
    normalised = normalize_image(path)
    identifier = path.stem
    record = SourceRecord(
        identifier=identifier,
        path=path,
        width=normalised.width,
        height=normalised.height,
        mode=normalised.mode,
        sha256=_sha256_of_path(path),
    )
    return record, normalised.pixels


def _write_scrambled(
    destination: Path,
    pixels: np.ndarray,
    rounds: int,
    algorithm_version: int,
    mode: str,
) -> None:
    metadata = MosaicMetadata(
        schema_version=1,
        app_marker="reversible_mosaic",
        operation_type="encrypted",
        algorithm_version=algorithm_version,
        rounds=rounds,
        pixel_mode=mode,  # type: ignore[arg-type]
        width=pixels.shape[1],
        height=pixels.shape[0],
    )
    write_png(destination, pixels, metadata)


def _process_source(
    record: SourceRecord,
    pixels: np.ndarray,
    output_root: Path,
) -> list[dict[str, object]]:
    descriptor = get(1)
    per_image_root = output_root / record.identifier
    per_image_root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(record.path, per_image_root / f"source{record.path.suffix.lower()}")
    rows: list[dict[str, object]] = []
    for seed_label, seed_value in CANONICAL_SEEDS:
        for rounds in ROUNDS:
            scrambled = descriptor.encrypt(pixels.copy(), seed_value, rounds, None)
            metrics = compute_metrics(pixels, scrambled)
            output_name = f"rounds_{rounds:02d}_seed_{seed_label}.png"
            _write_scrambled(
                per_image_root / output_name,
                scrambled,
                rounds,
                descriptor.version,
                record.mode,
            )
            rows.append(
                {
                    "image_id": record.identifier,
                    "seed_label": seed_label,
                    "seed": seed_value,
                    "rounds": rounds,
                    "output": str(Path(record.identifier) / output_name),
                    **metrics.as_dict(),
                }
            )
    return rows


def _render_scorecard(records: list[SourceRecord], destination: Path) -> None:
    header = (
        "# V1 视觉验收记分表（3 名检查者独立填写）\n\n"
        "> §12.3.4 / §12.3.5：每张图 1/5/10/20 轮各评一次；至少 2 人认定主要\n"
        "> 人脸、文字或主体轮廓难以直接辨认方可通过。纯色、1×1、全透明等低\n"
        "> 信息图片仅验收可逆性，不参与视觉隐藏能力判定。\n\n"
        "评分标记：`✓` = 难以直接辨认，`✗` = 主要内容仍可辨认，`?` = 不确定。\n\n"
    )
    lines: list[str] = [header]
    for record in records:
        lines.append(
            f"## {record.identifier}  ({record.width}×{record.height} {record.mode})\n"
        )
        lines.append(f"- 原图 SHA-256: `{record.sha256}`\n")
        lines.append("\n| 轮数 | 分享代码 | 检查者 1 | 检查者 2 | 检查者 3 | 备注 |\n")
        lines.append("|---|---|---|---|---|---|\n")
        for seed_label, seed_value in CANONICAL_SEEDS:
            for rounds in ROUNDS:
                lines.append(
                    f"| {rounds:>2} | {seed_value} ({seed_label}) |  |  |  |  |\n"
                )
        lines.append("\n")
    destination.write_text("".join(lines), encoding="utf-8")


def _summarise(metrics_rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    grouped: dict[tuple[int, str], list[dict[str, object]]] = {}
    for row in metrics_rows:
        key = (int(row["rounds"]), str(row["seed_label"]))
        grouped.setdefault(key, []).append(row)
    summary: dict[str, dict[str, float]] = {}
    for (rounds, seed_label), rows in sorted(grouped.items()):
        pixel_change = [float(row["pixel_change_rate"]) for row in rows]
        horizontal = [float(row["horizontal_correlation"]) for row in rows]
        vertical = [float(row["vertical_correlation"]) for row in rows]
        diagonal = [float(row["diagonal_correlation"]) for row in rows]
        edge = [float(row["edge_similarity"]) for row in rows]
        summary[f"rounds_{rounds:02d}_{seed_label}"] = {
            "images": float(len(rows)),
            "pixel_change_rate_mean": float(np.mean(pixel_change)),
            "pixel_change_rate_min": float(np.min(pixel_change)),
            "horizontal_correlation_abs_max": float(np.max(np.abs(horizontal))),
            "vertical_correlation_abs_max": float(np.max(np.abs(vertical))),
            "diagonal_correlation_abs_max": float(np.max(np.abs(diagonal))),
            "edge_similarity_max": float(np.max(edge)),
        }
    return summary


def build_review_bundle(sources: Path, output_root: Path) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    records: list[SourceRecord] = []
    all_rows: list[dict[str, object]] = []
    for source_path in _iter_source_images(sources):
        record, pixels = _load_source(source_path)
        records.append(record)
        all_rows.extend(_process_source(record, pixels, output_root))
    document = {
        "algorithm_version": 1,
        "algorithm_backend": v1_implementation(),
        "canonical_seeds": [
            {"label": label, "seed": seed} for label, seed in CANONICAL_SEEDS
        ],
        "rounds": list(ROUNDS),
        "sources": [
            {
                "identifier": record.identifier,
                "width": record.width,
                "height": record.height,
                "mode": record.mode,
                "sha256": record.sha256,
                "original_path": str(record.path),
            }
            for record in records
        ],
        "rows": all_rows,
        "summary": _summarise(all_rows),
    }
    (output_root / "metrics.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _render_scorecard(records, output_root / "scorecard.md")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("artifacts/visual_review_sources"),
        help="固定视觉图集输入目录",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/visual_review"),
        help="视觉验收产物输出目录",
    )
    return parser.parse_args()


def main() -> None:
    arguments = _parse_arguments()
    build_review_bundle(arguments.sources, arguments.output)


if __name__ == "__main__":
    main()
