"""App-level navigation keyboard handling tests."""

from __future__ import annotations

import pytest

pytest.importorskip("kivy")

from reversible_mosaic.app import ReversibleMosaicApp


class _Root:
    def __init__(self, current: str) -> None:
        self.current = current
        self.current_screen = self
        self.home_calls = 0

    def _go_home(self) -> None:
        self.home_calls += 1


def test_android_back_only_returns_form_and_tutorial_pages_home() -> None:
    app = ReversibleMosaicApp()
    for name in ("encode", "decode", "tutorial"):
        root = _Root(name)
        app.root = root
        assert app._on_keyboard(None, 27, 0, "", []) is True
        assert root.home_calls == 1

    for name in ("home", "progress", "result"):
        root = _Root(name)
        app.root = root
        assert app._on_keyboard(None, 27, 0, "", []) is False
        assert root.home_calls == 0


def test_non_back_key_is_not_consumed() -> None:
    app = ReversibleMosaicApp()
    root = _Root("encode")
    app.root = root

    assert app._on_keyboard(None, 13, 0, "", []) is False
    assert root.home_calls == 0
