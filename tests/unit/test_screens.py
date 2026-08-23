"""Widget-level checks for the operation-specific encode/decode form actions."""

from __future__ import annotations

import pytest

pytest.importorskip("kivy")

from reversible_mosaic.ui.screens import DecodeScreen, EncodeScreen


def _buttons_with_text(screen: EncodeScreen | DecodeScreen, text: str) -> list[object]:
    return [widget for widget in screen.walk() if getattr(widget, "text", None) == text]


def test_encode_keeps_random_share_code_action() -> None:
    screen = EncodeScreen()

    assert len(_buttons_with_text(screen, "随机 6 位")) == 1
    assert len(_buttons_with_text(screen, "清除")) == 1


def test_decode_only_shows_wide_clear_share_code_action() -> None:
    screen = DecodeScreen()

    assert _buttons_with_text(screen, "随机 6 位") == []
    clear_buttons = _buttons_with_text(screen, "清除")
    assert len(clear_buttons) == 1

    clear_button = clear_buttons[0]
    assert clear_button.size_hint_x == 2
    assert [child.text for child in clear_button.parent.children] == ["清除"]
