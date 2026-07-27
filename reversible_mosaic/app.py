"""Application shell with local-only product guidance."""

from __future__ import annotations

try:
    from kivy.lang import Builder
    from kivy.properties import StringProperty
    from kivy.uix.screenmanager import Screen
    from kivymd.app import MDApp
except ImportError as exc:  # pragma: no cover - friendly optional dependency boundary
    raise RuntimeError("请安装 app 依赖后启动界面: pip install -e '.[app]'") from exc

_KV = r"""
#:import dp kivy.metrics.dp

<HomeScreen>:
    name: "home"
    MDBoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(16)
        MDLabel:
            text: "ReversibleMosaic"
            font_style: "H4"
            adaptive_height: True
        MDLabel:
            text: "所有图片仅在本机处理"
            theme_text_color: "Secondary"
            adaptive_height: True
        Widget:
        MDRaisedButton:
            text: "打码"
            size_hint_x: 1
            height: dp(52)
            on_release: app.open_placeholder("打码")
        MDRaisedButton:
            text: "恢复"
            size_hint_x: 1
            height: dp(52)
            on_release: app.open_placeholder("恢复")
        MDRectangleFlatButton:
            text: "教程与安全边界"
            size_hint_x: 1
            height: dp(52)
            on_release: app.root.current = "tutorial"

<TutorialScreen>:
    name: "tutorial"
    MDBoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(16)
        MDLabel:
            text: "使用说明"
            font_style: "H5"
            adaptive_height: True
        MDLabel:
            text: root.tutorial_text
            valign: "top"
        MDRectangleFlatButton:
            text: "返回首页"
            size_hint_x: 1
            height: dp(52)
            on_release: app.root.current = "home"

<PlaceholderScreen>:
    name: "placeholder"
    MDBoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(16)
        MDLabel:
            text: root.title
            font_style: "H5"
            adaptive_height: True
        MDLabel:
            text: "核心算法与文件链路正在验证。本页面不会上传或保存图片历史。"
        MDRectangleFlatButton:
            text: "返回首页"
            size_hint_x: 1
            height: dp(52)
            on_release: app.root.current = "home"

MDScreenManager:
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


class ReversibleMosaicApp(MDApp):  # type: ignore[misc]
    """Root app; processing screens are added after the core gate passes."""

    def build(self):  # type: ignore[no-untyped-def]
        self.theme_cls.primary_palette = "BlueGray"
        self.theme_cls.theme_style = "Light"
        return Builder.load_string(_KV)

    def open_placeholder(self, title: str) -> None:
        screen = self.root.get_screen("placeholder")
        screen.title = title
        self.root.current = "placeholder"
