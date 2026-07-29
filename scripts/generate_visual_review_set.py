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
    """Emit a single-reviewer scorecard covering 20 images x 4 rounds = 80 rows.

    MVP deviation (§12.3 revised 2026-07-29): 单人验收 + 自动指标双重校验。
    Scorecard only lists the default share code (500000); multi-seed metrics
    stay in ``metrics.json`` for the §12.3.6 diverse-seed check, which is a
    numeric comparison, not a human judgement.
    """
    default_seed_label, default_seed_value = CANONICAL_SEEDS[0]
    header = (
        "# V1 视觉验收记分表 (单人 MVP 变体)\n\n"
        "> **验收协议**：需求档 §12.3 修订 2026-07-29 单人偏差 —— 由本记分表\n"
        "> 单一检查者 (通常为产品负责人) 独立打分 + `metrics.json` 三项自动指标\n"
        "> 双重校验。原 §12.3.4-5 的 3 名检查者判定条款仅在公开发布或商业推出\n"
        "> 前须重新组织时恢复。\n\n"
        "**你要做什么**：对每张原图，看 4 张打码后的输出图，独立判断\n"
        "**是否难以直接辨认主体 / 文字 / 人脸**。\n\n"
        "**评分标记**：\n"
        "- `✓` = 主要内容 (人脸、文字、场景主体) 已难以直接辨认 (通过)。\n"
        "- `✗` = 主要内容仍可直接辨认 (失败；需在备注写清哪部分残留)。\n"
        "- `?` = 不确定 / 内容边界感 (记为不通过，重跑此张)。\n\n"
        f"**分享代码固定为 `{default_seed_value}` (default)**；\n"
        "其他 seed 变体只影响 metrics.json 里的多 seed 差异指标。\n\n"
        "---\n\n"
    )
    lines: list[str] = [header]
    for record in records:
        lines.append(
            f"## {record.identifier}  ({record.width}×{record.height} {record.mode})\n"
        )
        lines.append(f"- 原图 SHA-256: `{record.sha256}`\n")
        lines.append(
            f"- 打码结果目录: `{record.identifier}/rounds_XX_seed_{default_seed_label}.png`\n"
        )
        lines.append("\n| 轮数 | 打码文件 | 判定 | 备注 |\n")
        lines.append("|---|---|:-:|---|\n")
        for rounds in ROUNDS:
            output_name = f"rounds_{rounds:02d}_seed_{default_seed_label}.png"
            lines.append(f"| {rounds:>2} | `{output_name}` |  |  |\n")
        lines.append("\n")
    lines.append(
        "---\n\n"
        "## 汇总\n\n"
        "填完后统计一下：\n\n"
        "- **通过判定 (`✓`)**：____ / 80\n"
        "- **失败判定 (`✗` 或 `?`)**：____ / 80\n"
        "- **每张至少一轮通过**：____ / 20\n"
        "- **每张 1/5/10/20 全通过**：____ / 20\n\n"
        "**发布决策规则**：\n\n"
        "1. 5/10/20 轮**每张至少 15/20 张通过** (即失败 ≤ 5 张) → 视觉隐藏能力\n"
        "   达标。\n"
        "2. 1 轮未通过不影响发布 (1 轮定位为 sanity check)，但需在报告中\n"
        "   注明比例。\n"
        "3. 若某分享代码在 ≥3 张内容丰富图上都失败 → §12.3.6 系统性退化，\n"
        "   V1 不得发布 (需增派)。\n"
        "4. `metrics.json` 三项自动指标必须同时通过冻结阈值 (见\n"
        "   `docs/algorithm-v1.md` 附录)。\n\n"
        "**检查者签署**：\n\n"
        "- 姓名 / 花名：____________\n"
        "- 日期：____________\n"
        "- 备注：____________\n"
    )
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
