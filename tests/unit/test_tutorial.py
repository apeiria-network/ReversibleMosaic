"""Tests for the user-facing, styled in-app tutorial."""

from __future__ import annotations

import pytest

pytest.importorskip("kivy", reason="tutorial screen requires kivy from .[app]")

from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView

from reversible_mosaic.ui.tutorial import (
    TUTORIAL_ASSET_DIR,
    TUTORIAL_BLOCKS,
    TUTORIAL_IMAGE_FILENAMES,
    TutorialScreen,
    _PreviewGestureLayer,
    _PreviewScatter,
    _TutorialImageButton,
    _TutorialImagePreview,
)


def _tutorial_text() -> str:
    return "\n".join(block.text for block in TUTORIAL_BLOCKS)


def test_tutorial_contains_only_user_facing_sections() -> None:
    text = _tutorial_text()

    for heading in ("APP 使用效果", "快速开始", "APP 功能", "使用限制与建议", "项目定位"):
        assert heading in text

    assert "给开发者的信息" not in text
    assert "developer_docs" not in text
    assert "docs/" not in text
    assert "http://" not in text
    assert "https://" not in text


def test_tutorial_images_are_referenced_and_packaged() -> None:
    referenced_images = tuple(
        block.image_filename for block in TUTORIAL_BLOCKS if block.kind == "image"
    )

    assert referenced_images == TUTORIAL_IMAGE_FILENAMES
    for filename in TUTORIAL_IMAGE_FILENAMES:
        path = TUTORIAL_ASSET_DIR / filename
        assert path.is_file(), f"missing tutorial asset: {path}"
        assert path.stat().st_size > 0


def test_tutorial_share_code_guidance_matches_default_flow() -> None:
    text = _tutorial_text()

    assert "默认值为 500000" in text
    assert "通常不需要修改" in text
    assert "无需用户填入" in text
    assert "只有打码时修改过代码" in text
    assert "随机 6 位" in text


def test_tutorial_excludes_removed_image_sharing_feature() -> None:
    text = _tutorial_text()

    assert "Android 系统分享功能" not in text
    assert "调用 Android 系统分享" not in text
    assert "保存到手机" in text
    assert "可信渠道" in text

    screen = TutorialScreen(name="tutorial")
    descendants = list(screen.walk())

    assert any(isinstance(widget, ScrollView) for widget in descendants)
    assert sum(isinstance(widget, Image) for widget in descendants) == len(
        TUTORIAL_IMAGE_FILENAMES
    )
    assert any(
        isinstance(widget, Button) and widget.text == "返回首页" for widget in descendants
    )
    assert sum(isinstance(widget, _TutorialImageButton) for widget in descendants) == len(
        TUTORIAL_IMAGE_FILENAMES
    )


def test_tutorial_image_preview_supports_clean_zoom_pan_layout() -> None:
    preview = _TutorialImagePreview(
        source=str(TUTORIAL_ASSET_DIR / TUTORIAL_IMAGE_FILENAMES[0]),
    )
    descendants = list(preview.walk())
    scatter = next(widget for widget in descendants if isinstance(widget, _PreviewScatter))
    gesture_layer = next(
        widget for widget in descendants if isinstance(widget, _PreviewGestureLayer)
    )
    assert callable(gesture_layer._on_tap)

    assert scatter.do_scale is True
    assert scatter.do_translation == (True, True)
    assert scatter.do_rotation is False
    assert scatter.scale_min == 1.0
    assert scatter.scale_max == 5.0
    assert not any(isinstance(widget, Button) and widget.text == "关闭" for widget in descendants)
    assert all("双指拖动/缩放" not in getattr(widget, "text", "") for widget in descendants)
    preview.dismiss()


    preview.dismiss()


def test_preview_gesture_layer_dismisses_screen_tap_but_not_drag_or_pinch() -> None:
    layer = _PreviewGestureLayer(on_tap=lambda: None)

    layer._begin_interaction(1, (5, 5))
    assert layer._finish_interaction(1) is True

    layer._begin_interaction(2, (5, 5))
    layer._move_interaction(2, (5 + dp(9), 5))
    assert layer._finish_interaction(2) is False

    layer._begin_interaction(3, (5, 5))
    layer._begin_interaction(4, (10, 10))
    assert layer._finish_interaction(4) is False
    assert layer._finish_interaction(3) is False


    scatter = _PreviewScatter(on_tap=lambda: None)

    scatter._begin_interaction(1, (100, 100))
    assert scatter._finish_interaction(1) is True

    scatter._begin_interaction(2, (100, 100))
    scatter._move_interaction(2, (100 + dp(9), 100))
    assert scatter._finish_interaction(2) is False

    scatter._begin_interaction(3, (100, 100))
    scatter._begin_interaction(4, (120, 100))
    scatter._move_interaction(3, (105, 100))
    scatter._move_interaction(4, (125, 100))
    assert scatter._finish_interaction(4) is False
    assert scatter._finish_interaction(3) is False

    scatter._begin_interaction(5, (100, 100))
    assert scatter._finish_interaction(5) is True
