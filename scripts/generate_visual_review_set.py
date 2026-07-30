"""Generate the pre-freeze visual review artefact bundle for V1.

Usage:

    python scripts/generate_visual_review_set.py \\
        --sources artifacts/visual_review_sources \\
        --output  artifacts/visual_review

For each image in ``--sources`` (RGB/RGBA PNG or plain RGB JPEG) the script:

1. Normalises the input (EXIF Orientation, mode conversion, resource limits).
2. Runs V1 encryption at rounds 2, 5, 15, 30 with a canonical seed set
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
ROUNDS: tuple[int, ...] = (2, 5, 15, 30)


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

    Round-differentiated criteria (2026-07-29 revised by product owner):
    each round has a distinct target — 2 hides details, 5 is hard to
    recognize, 15 and 30 must be unrecognizable. The scorecard makes each
    row explicit about which bar it is measured against.
    """
    default_seed_label, default_seed_value = CANONICAL_SEEDS[0]
    round_criteria: dict[int, tuple[str, str]] = {
        2: ("细节已隐去", "纹理 / 小文字 / 小物件 / 装饰细节看不见；主体轮廓允许仍可识别"),
        5: ("较难辨认", "主体较难辨认；需仔细看才能识别；文字不可读；人脸细节丢失"),
        15: ("无法辨认", "无法直接辨认主体 / 文字 / 人脸"),
        30: ("无法辨认", "无法直接辨认主体 / 文字 / 人脸"),
    }
    header = (
        "# V1 视觉验收记分表 (单人 MVP 变体)\n\n"
        "> **验收协议**：需求档 §12.3 修订 2026-07-29 单人偏差 —— 由本记分表\n"
        "> 单一检查者 (通常为产品负责人) 独立打分 + `metrics.json` 三项自动指标\n"
        "> 双重校验。原 §12.3.4-5 的 3 名检查者判定条款仅在公开发布或商业推出\n"
        "> 前须重新组织时恢复。\n\n"
        "## 评分标准 (分轮次差异化, 2026-07-29 修订)\n\n"
        "**每一轮有不同的通过门槛**，反映 `docs/algorithm-v1.md` §A.6 的定位。\n"
        "对每张原图看 4 张打码输出，按当前轮次的目标独立判定：\n\n"
        "| 轮数 | 目标定位 | 通过 (✓) 判定 |\n"
        "|---|---|---|\n"
        f"|  2 | Sanity check — 遮盖细节 | {round_criteria[2][1]} |\n"
        f"|  5 | MVP 默认 — 较难辨认 | {round_criteria[5][1]} |\n"
        f"| 15 | 主档 — 无法辨认 | {round_criteria[15][1]} |\n"
        f"| 30 | 最高档 — 无法辨认 | {round_criteria[30][1]} |\n\n"
        "**评分标记**（2026-07-29 由检查者定制的 0/1/2/3 数字体系）：\n"
        "- `2` = 满足**当前轮次**的通过判定 (通过)。\n"
        "- `0` = 未满足 (失败；请在备注写清残留了哪部分)。\n"
        "- `1` = 不确定 / 边界感 (记为不通过)。\n"
        "- `3` = 模糊度过高，无法辨认 (记为通过)。\n\n"
        f"**分享代码固定为 `{default_seed_value}` (default)**；其他 seed 变体只影响\n"
        "`metrics.json` 里的多 seed 差异指标。\n\n"
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
        lines.append("\n| 轮数 | 目标 | 打码文件 | 判定 | 备注 |\n")
        lines.append("|---|---|---|:-:|---|\n")
        for rounds in ROUNDS:
            output_name = f"rounds_{rounds:02d}_seed_{default_seed_label}.png"
            target = round_criteria[rounds][0]
            lines.append(f"| {rounds:>2} | {target} | `{output_name}` |  |  |\n")
        lines.append("\n")
    lines.append(
        "---\n\n"
        "## 汇总\n\n"
        "填完后按**分轮次**统计（每一档目标不同，不再汇总成单一分子）：\n\n"
        "- **2 轮 (`细节已隐去`)**：____ / 20 通过\n"
        "- **5 轮 (`较难辨认`)**：____ / 20 通过\n"
        "- **15 轮 (`无法辨认`)**：____ / 20 通过\n"
        "- **30 轮 (`无法辨认`)**：____ / 20 通过\n\n"
        "**发布决策规则**（2026-07-29 修订，轮次集 {2, 5, 15, 30}）：\n\n"
        "1. **2 轮 ≥ 15/20 通过** → sanity check 层达标。\n"
        "2. **5 轮 ≥ 15/20 通过** → MVP 默认档达标（发布阻断项）。\n"
        "3. **15 轮 ≥ 16/20 通过** → 主档达标（发布阻断项，2026-07-29 定稿\n"
        "   实测 16/20；p16 类小尺寸图靠 30 轮兜底）。\n"
        "4. **30 轮 ≥ 20/20 通过** → 最高档达标（严格 20/20 完美要求）。\n"
        "5. 若同一分享代码在 ≥3 张内容丰富图上都失败 → §12.3.6 系统性退化，\n"
        "   V1 不得发布。\n"
        "6. `metrics.json` 三项自动指标必须同时通过冻结阈值（见\n"
        "   `docs/algorithm-v1.md` §A.13 附录，冻结时敲定）。\n\n"
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
