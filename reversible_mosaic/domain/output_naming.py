"""Output filename helpers.

Compute the human-friendly filename we hand to MediaStore / the local cache
based on the ORIGINAL input filename plus a mosaic/reversal suffix:

- ``photo.jpg``   +  encrypt →  ``photo_mosaic.png``
- ``photo.png``   +  decrypt →  ``photo_reversal_mosaic.png``
- ``photo.jpg``   +  encrypt (twice) → ``photo_mosaic.png``, ``photo_mosaic_1.png``

Duplicate handling scans a *predicate* callback so the same logic covers both
"file exists in cache dir" and "MediaStore already has this DISPLAY_NAME under
this RELATIVE_PATH". Callers pass a lambda that answers "is this name taken?".

Fallback: when ``original_display_name`` is None or blank we synthesize
``mosaic_yyyymmdd_hhmmss[_Rn].png`` / ``reversal_mosaic_yyyymmdd_hhmmss.png``
so we never leak the app-cache's random ``pick_<ts>.jpg`` name to the gallery.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from time import strftime

_ENCRYPT_SUFFIX = "_mosaic"
_DECRYPT_SUFFIX = "_reversal_mosaic"
_MAX_STEM_BYTES = 96  # keep MediaStore display names short + human-readable

# Reserved on Windows / illegal in most filesystems + control chars.
_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_stem(raw: str) -> str:
    """Reduce a raw filename stem to a safe MediaStore DISPLAY_NAME base.

    - Substitutes reserved chars (``< > : " / \\ | ? *`` and control chars) with
      ``_`` BEFORE any path parsing so ``/`` doesn't silently drop directory
      segments and lose the actual filename.
    - Runs ``Path.stem`` on the sanitized string to drop the extension.
    - Collapses whitespace, trims leading/trailing dots/dashes/underscores.
    - Caps to ``_MAX_STEM_BYTES`` (UTF-8 byte-safe truncation).
    """
    substituted = _UNSAFE_RE.sub("_", raw)
    stem = Path(substituted).stem or substituted
    stem = re.sub(r"\s+", "_", stem)
    stem = re.sub(r"_+", "_", stem)
    stem = stem.strip("._-")
    if not stem:
        return ""
    encoded = stem.encode("utf-8")
    if len(encoded) > _MAX_STEM_BYTES:
        stem = encoded[:_MAX_STEM_BYTES].decode("utf-8", errors="ignore").rstrip("._-")
        if not stem:
            return ""
    return stem


def _base_stem(original_display_name: str | None, operation: str) -> str:
    """Return the base stem (before collision handling)."""
    fallback_prefix = "mosaic" if operation == "encrypted" else "reversal_mosaic"
    if original_display_name:
        cleaned = sanitize_stem(original_display_name)
        if cleaned:
            suffix = _ENCRYPT_SUFFIX if operation == "encrypted" else _DECRYPT_SUFFIX
            return f"{cleaned}{suffix}"
    return f"{fallback_prefix}_{strftime('%Y%m%d_%H%M%S')}"


def compute_output_name(
    original_display_name: str | None,
    *,
    operation: str,
    name_taken: Callable[[str], bool] | None = None,
    max_attempts: int = 999,
) -> str:
    """Return a ``<stem>_mosaic[_N].png``-style filename.

    ``name_taken`` is called with candidate filenames (e.g. ``photo_mosaic.png``,
    ``photo_mosaic_1.png``, …). The first candidate for which it returns
    ``False`` wins. If it is ``None``, the base name is returned unmodified.
    """
    base_stem = _base_stem(original_display_name, operation)
    candidate = f"{base_stem}.png"
    if name_taken is None or not name_taken(candidate):
        return candidate
    for n in range(1, max_attempts + 1):
        candidate = f"{base_stem}_{n}.png"
        if not name_taken(candidate):
            return candidate
    # Extremely unlikely; still emit a unique-enough fallback rather than raise
    # so the caller can proceed. MediaStore will resolve conflicts on its side.
    return f"{base_stem}_{strftime('%Y%m%d_%H%M%S')}.png"


__all__ = ["compute_output_name", "sanitize_stem"]
