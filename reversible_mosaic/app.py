"""Application shell with local-only product guidance.

Phase-0 probe uses plain Kivy widgets only. KivyMD (and the polished styling
that comes with it) is deferred to a later probe iteration, after the arm64
toolchain is proven end-to-end.
"""

from __future__ import annotations

from pathlib import Path

try:
    from kivy.app import App
    from kivy.core.text import LabelBase
    from kivy.lang import Builder
    from kivy.properties import StringProperty
    from kivy.uix.screenmanager import Screen
except ImportError as exc:  # pragma: no cover - friendly optional dependency boundary
    raise RuntimeError("请安装 app 依赖后启动界面: pip install -e '.[app]'") from exc


_CJK_FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "wqy-microhei.ttc"
if _CJK_FONT_PATH.is_file():
    # Replace Kivy's default "Roboto" so unmarked Label widgets render both
    # Latin and CJK glyphs. WenQuanYi Micro Hei covers ASCII + simplified
    # Chinese; keep the "Roboto" name so widgets that omit font_name pick it up.
    LabelBase.register(name="Roboto", fn_regular=str(_CJK_FONT_PATH))


_KV = r"""
#:import dp kivy.metrics.dp

<HomeScreen>:
    name: "home"
    BoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(16)
        Label:
            text: "ReversibleMosaic"
            font_size: dp(28)
            size_hint_y: None
            height: dp(56)
        Label:
            text: "所有图片仅在本机处理"
            font_size: dp(16)
            color: 0.6, 0.6, 0.6, 1
            size_hint_y: None
            height: dp(32)
        Widget:
        Button:
            text: "打码"
            size_hint_y: None
            height: dp(52)
            on_release: app.open_placeholder("打码")
        Button:
            text: "恢复"
            size_hint_y: None
            height: dp(52)
            on_release: app.open_placeholder("恢复")
        Button:
            text: "教程与安全边界"
            size_hint_y: None
            height: dp(52)
            on_release: app.root.current = "tutorial"

<TutorialScreen>:
    name: "tutorial"
    BoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(16)
        Label:
            text: "使用说明"
            font_size: dp(22)
            size_hint_y: None
            height: dp(48)
        Label:
            text: root.tutorial_text
            text_size: self.width, None
            valign: "top"
            halign: "left"
        Button:
            text: "返回首页"
            size_hint_y: None
            height: dp(52)
            on_release: app.root.current = "home"

<PlaceholderScreen>:
    name: "placeholder"
    BoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(16)
        Label:
            text: root.title
            font_size: dp(22)
            size_hint_y: None
            height: dp(48)
        Label:
            text: "核心算法与文件链路正在验证。本页面不会上传或保存图片历史。"
            text_size: self.width, None
            valign: "top"
            halign: "left"
        Button:
            text: "返回首页"
            size_hint_y: None
            height: dp(52)
            on_release: app.root.current = "home"

ScreenManager:
    HomeScreen:
    TutorialScreen:
    PlaceholderScreen:
"""


class HomeScreen(Screen):  # type: ignore[misc]
    pass


class TutorialScreen(Screen):  # type: ignore[misc]
    tutorial_text = StringProperty(
        "1. 选择图片并确认轮数。\n"
        "2. 妥善记录规范化分享代码; App 不保存也无法找回。\n"
        "3. 恢复时算法版本、轮数和分享代码必须匹配。\n"
        "4. 必须以文件/原图传播; 截图、裁剪或转码后不保证恢复。\n"
        "5. 本产品是可逆视觉混淆, 不是密码学加密。"
    )


class PlaceholderScreen(Screen):  # type: ignore[misc]
    title = StringProperty("")


class ReversibleMosaicApp(App):  # type: ignore[misc]
    """Root app; processing screens are added after the core gate passes."""

    def build(self):  # type: ignore[no-untyped-def]
        return Builder.load_string(_KV)

    def open_placeholder(self, title: str) -> None:
        screen = self.root.get_screen("placeholder")
        screen.title = title
        self.root.current = "placeholder"
