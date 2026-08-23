"""Widget-level checks for the operation-specific encode/decode form actions."""

from __future__ import annotations

import pytest

pytest.importorskip("kivy")

# ruff: noqa: RUF001

from kivy.uix.label import Label

from reversible_mosaic.ui.screens import DecodeScreen, EncodeScreen, ResultScreen


def _buttons_with_text(
    screen: EncodeScreen | DecodeScreen | ResultScreen, text: str
) -> list[object]:
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


def test_encode_and_decode_group_parameters_with_extra_spacing() -> None:
    for screen, labels in (
        (EncodeScreen(), {"轮数（轮数越多，打码效果越好）", "分享代码 (留空使用默认 500000)"}),
        (
            DecodeScreen(),
            {"算法版本", "轮数（轮数越多，打码效果越好）", "分享代码 (留空使用默认 500000)"},
        ),
    ):
        parameter_labels = {
            widget.text: widget
            for widget in screen.walk()
            if isinstance(widget, Label) and widget.text in labels
        }

        assert set(parameter_labels) == labels
        for label in parameter_labels.values():
            block = label.parent
            assert block.orientation == "vertical"
            assert block.padding[1] > 0
            assert block.padding[3] > 0
            assert block.spacing > 0


def test_edge_swipe_returns_encode_decode_screen_home() -> None:
    for screen in (EncodeScreen(), DecodeScreen()):
        screen.width = 360

        screen._begin_home_swipe(1, (0, 200))
        assert screen._finish_home_swipe(1, (100, 205)) is True

        screen._begin_home_swipe(2, (0, 200))
        assert screen._finish_home_swipe(2, (20, 300)) is False

        screen._begin_home_swipe(3, (0, 200))
        screen._begin_home_swipe(4, (20, 200))
        assert screen._finish_home_swipe(3, (80, 200)) is False


    screen = ResultScreen()

    save_buttons = _buttons_with_text(screen, "保存到相册")
    view_buttons = _buttons_with_text(screen, "查看")

    assert len(save_buttons) == 1
    assert len(view_buttons) == 1
    assert _buttons_with_text(screen, "原图/文件分享") == []

    save_button = save_buttons[0]
    view_button = view_buttons[0]
    assert save_button.parent is view_button.parent
    assert [child.text for child in save_button.parent.children] == [
        "查看",
        "保存到相册",
    ]
    assert save_button.size_hint_x == view_button.size_hint_x
