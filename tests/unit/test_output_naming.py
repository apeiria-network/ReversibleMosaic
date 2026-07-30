"""Tests for :mod:`reversible_mosaic.domain.output_naming`.

Covers the ``<stem>_mosaic[_N].png`` collision walk, the ``_reversal_mosaic``
decode suffix, the sanitize path (illegal chars / whitespace / control chars
/ length cap), and the timestamped fallback when no display name is available.
"""

from __future__ import annotations

from reversible_mosaic.domain.output_naming import compute_output_name, sanitize_stem


def test_encrypt_uses_mosaic_suffix() -> None:
    name = compute_output_name("holiday.jpg", operation="encrypted", name_taken=None)
    assert name == "holiday_mosaic.png"


def test_decrypt_uses_reversal_suffix() -> None:
    name = compute_output_name("cat.PNG", operation="restored", name_taken=None)
    assert name == "cat_reversal_mosaic.png"


def test_collision_increments_suffix() -> None:
    taken = {"holiday_mosaic.png", "holiday_mosaic_1.png"}
    name = compute_output_name(
        "holiday.jpg", operation="encrypted", name_taken=lambda n: n in taken
    )
    assert name == "holiday_mosaic_2.png"


def test_no_display_name_uses_timestamped_fallback() -> None:
    encrypted = compute_output_name(None, operation="encrypted", name_taken=None)
    restored = compute_output_name("", operation="restored", name_taken=None)
    assert encrypted.startswith("mosaic_") and encrypted.endswith(".png")
    assert restored.startswith("reversal_mosaic_") and restored.endswith(".png")


def test_sanitize_stem_removes_reserved_chars() -> None:
    assert sanitize_stem('bad<name>:"/\\|?*.png') == "bad_name"


def test_sanitize_stem_collapses_whitespace() -> None:
    assert sanitize_stem("  hello   world  .jpg") == "hello_world"


def test_sanitize_stem_strips_control_chars() -> None:
    assert sanitize_stem("photo\x00\x01.png") == "photo"


def test_sanitize_stem_caps_length() -> None:
    long = "x" * 300 + ".png"
    result = sanitize_stem(long)
    assert 0 < len(result.encode("utf-8")) <= 96
    assert result.startswith("x")


def test_sanitize_stem_empty_stays_empty() -> None:
    assert sanitize_stem("") == ""
    assert sanitize_stem(".hidden") == "hidden"


def test_collision_walk_stops_at_max_attempts() -> None:
    # Every name is taken → falls back to a timestamped suffix rather than
    # spinning forever.
    result = compute_output_name(
        "photo.jpg",
        operation="encrypted",
        name_taken=lambda _n: True,
        max_attempts=3,
    )
    assert result.startswith("photo_mosaic_")
    assert result.endswith(".png")


def test_display_name_with_path_traversal_is_stripped() -> None:
    """A malicious display name must never leak path separators upstream."""
    result = compute_output_name(
        "../../etc/passwd", operation="encrypted", name_taken=None
    )
    # sanitize_stem must not emit ``/`` or ``\``; the file must remain PNG.
    assert "/" not in result
    assert "\\" not in result
    assert result.endswith(".png")


def test_absolute_windows_path_is_stripped() -> None:
    result = compute_output_name(
        r"C:\Users\alice\secret.jpg", operation="encrypted", name_taken=None
    )
    assert "\\" not in result and "/" not in result
    assert ":" not in result
    assert result.endswith(".png")
