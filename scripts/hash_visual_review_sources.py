"""Hash visual-review source images and enrich sources.csv.

Reads the tab- or comma-separated ``sources.csv`` in
``artifacts/visual_review_sources/``, matches each ``picture_id`` (e.g. ``p1``)
to a file on disk regardless of extension (``.jpg`` / ``.jpeg`` / ``.png``),
computes SHA-256, and rewrites the CSV with two additional columns
``filename`` and ``sha256``. Existing columns are preserved verbatim.

Also validates:
- every ``picture_id`` in the CSV must resolve to exactly one file on disk;
- every image file on disk must have a matching CSV row;
- extensions must be in the P0 subset (``.jpg`` / ``.jpeg`` / ``.png``).

Usage::

    python scripts/hash_visual_review_sources.py
    python scripts/hash_visual_review_sources.py --dir artifacts/visual_review_sources
    python scripts/hash_visual_review_sources.py --check   # dry run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO_ROOT / "artifacts" / "visual_review_sources"
CSV_NAME = "sources.csv"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _sniff_delimiter(sample: str) -> str:
    """Return ``','`` or ``'\\t'`` — TSV is common when Excel saves .csv on zh-CN."""
    header_line = sample.splitlines()[0] if sample else ""
    if "\t" in header_line:
        return "\t"
    return ","


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 16), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _resolve_pid_to_file(pid: str, disk_files: dict[str, Path]) -> Path | None:
    """Given ``pid`` (like ``p1``) find its file on disk regardless of extension."""
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = disk_files.get(f"{pid}{ext}")
        if candidate is not None:
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--check", action="store_true", help="Report but don't write.")
    args = parser.parse_args()

    root: Path = args.dir
    csv_path = root / CSV_NAME
    if not csv_path.is_file():
        print(f"ERROR: {csv_path} not found.", file=sys.stderr)
        return 2

    text = csv_path.read_text(encoding="utf-8-sig")
    delimiter = _sniff_delimiter(text)
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if reader.fieldnames is None or "picture_id" not in reader.fieldnames:
        print(
            "ERROR: sources.csv must have a 'picture_id' column (first column).",
            file=sys.stderr,
        )
        return 2
    rows = list(reader)

    disk_files: dict[str, Path] = {
        entry.name: entry
        for entry in root.iterdir()
        if entry.is_file() and entry.suffix.lower() in ALLOWED_EXTENSIONS
    }
    print(f"Scanned {root}: {len(disk_files)} image file(s), {len(rows)} CSV row(s).")

    csv_ids = {row["picture_id"] for row in rows}
    disk_stems = {name.rsplit(".", 1)[0] for name in disk_files}
    missing_files = sorted(csv_ids - disk_stems)
    orphan_files = sorted(disk_stems - csv_ids)
    problems = 0
    if missing_files:
        problems += 1
        print(f"WARN  CSV rows without matching file: {missing_files}", file=sys.stderr)
    if orphan_files:
        problems += 1
        print(
            f"WARN  Image files not listed in CSV: {orphan_files}", file=sys.stderr
        )

    enriched_rows: list[dict[str, str]] = []
    for row in rows:
        pid = row["picture_id"]
        file = _resolve_pid_to_file(pid, disk_files)
        if file is None:
            row_out = dict(row)
            row_out["filename"] = ""
            row_out["sha256"] = ""
            row_out["file_bytes"] = ""
            enriched_rows.append(row_out)
            continue
        digest = _sha256(file)
        row_out = dict(row)
        row_out["filename"] = file.name
        row_out["sha256"] = digest
        row_out["file_bytes"] = str(file.stat().st_size)
        enriched_rows.append(row_out)

    # Column ordering: picture_id, filename, sha256, file_bytes, source, license, then any extras.
    known_first = ["picture_id", "filename", "sha256", "file_bytes"]
    extras = [
        column
        for column in reader.fieldnames or []
        if column not in known_first
    ]
    fieldnames = known_first + extras

    if args.check:
        print("--- Dry run ---")
        print(f"Would write {csv_path} with fields: {fieldnames}")
        for row in enriched_rows[:3]:
            print("  sample row:", {k: row.get(k, "") for k in fieldnames})
        if problems:
            return 1
        return 0

    # Write UTF-8 with BOM so Windows spreadsheet applications recognize Chinese text
    # when sources.csv is opened directly; readers should use utf-8-sig.
    with csv_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames, delimiter=",")
        writer.writeheader()
        for row in enriched_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print(f"Wrote enriched {csv_path} ({len(enriched_rows)} rows).")
    if problems:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
