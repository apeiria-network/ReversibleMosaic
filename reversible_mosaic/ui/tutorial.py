"""Scrollable, styled in-app tutorial content for ordinary ReversibleMosaic users.

This module deliberately maintains an app-specific copy of the user-facing README
content. It does not render arbitrary Markdown and it never exposes developer
document links inside the app.
"""

# ruff: noqa: RUF001

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

try:
    from kivy.clock import Clock
    from kivy.graphics import Color, Line, RoundedRectangle
    from kivy.metrics import dp
    from kivy.uix.behaviors import ButtonBehavior
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.floatlayout import FloatLayout
    from kivy.uix.image import Image
    from kivy.uix.label import Label
    from kivy.uix.modalview import ModalView
    from kivy.uix.scatter import Scatter
    from kivy.uix.screenmanager import Screen
    from kivy.uix.scrollview import ScrollView
except ImportError as exc:  # pragma: no cover - matches the application dependency boundary
    raise RuntimeError("请安装 app 依赖后启动界面: pip install -e '.[app]'") from exc


TUTORIAL_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "tutorial"
TUTORIAL_IMAGE_FILENAMES: tuple[str, ...] = (
    "example_compare.png",
    "app-home.png",
    "app-encrypted.png",
    "app-restored.png",
    "after-restored.png",
)


class _TutorialImageButton(ButtonBehavior, Image):  # type: ignore[misc]
    """A tutorial image that opens a larger, gesture-enabled preview."""

    def __init__(self, *, on_activate: Callable[[], object], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._on_activate = on_activate
        with self.canvas.after:
            self._border_color = Color(0, 0, 0, 1)
            self._border = Line(rectangle=(0, 0, 0, 0), width=dp(1))
        self.bind(pos=self._sync_border, size=self._sync_border)
        self._sync_border()

    def _sync_border(self, *_args: object) -> None:
        self._border.rectangle = (*self.pos, *self.size)

    def on_release(self) -> None:
        self._on_activate()


class _PreviewScatter(Scatter):  # type: ignore[misc]
    """Scatter that closes the modal only after an independent light tap."""

    def __init__(self, *, on_tap: Callable[[], None], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._on_tap = on_tap
        self._touch_starts: dict[int, tuple[float, float]] = {}
        self._moved = False
        self._multi_touch = False
        self._gesture_active = False

    def _begin_interaction(self, touch_id: int, position: tuple[float, float]) -> None:
        """Record one pointer joining the current interaction session."""
        if not self._gesture_active:
            self._touch_starts.clear()
            self._moved = False
            self._multi_touch = False
            self._gesture_active = True
        elif self._touch_starts:
            self._multi_touch = True
        self._touch_starts[touch_id] = position

    def _move_interaction(self, touch_id: int, position: tuple[float, float]) -> None:
        """Disqualify the session from tap-to-close after a visible drag."""
        start = self._touch_starts.get(touch_id)
        if start is None:
            return
        threshold = dp(8)
        if abs(position[0] - start[0]) > threshold or abs(position[1] - start[1]) > threshold:
            self._moved = True

    def _finish_interaction(self, touch_id: int) -> bool:
        """Finish a pointer and report whether the entire session was a tap."""
        if touch_id not in self._touch_starts:
            return False
        self._touch_starts.pop(touch_id)
        if self._touch_starts:
            return False

        should_close = self._gesture_active and not self._moved and not self._multi_touch
        self._gesture_active = False
        self._moved = False
        self._multi_touch = False
        return should_close

    def on_touch_down(self, touch: Any) -> bool:
        if not self.collide_point(*touch.pos):
            return False
        self._begin_interaction(id(touch), touch.pos)
        return bool(super().on_touch_down(touch))

    def on_touch_move(self, touch: Any) -> bool:
        self._move_interaction(id(touch), touch.pos)
        return bool(super().on_touch_move(touch))

    def on_touch_up(self, touch: Any) -> bool:
        handled = bool(super().on_touch_up(touch))
        if self._finish_interaction(id(touch)):
            Clock.schedule_once(lambda _dt: self._on_tap(), 0)
        return handled


class _TutorialImagePreview(ModalView):  # type: ignore[misc]
    """Near-full-screen preview with pan and pinch-to-zoom support."""

    def __init__(self, *, source: str, **kwargs: Any) -> None:
        super().__init__(
            auto_dismiss=False,
            background_color=(0.02, 0.02, 0.02, 0.96),
            size_hint=(1, 1),
            **kwargs,
        )
        self._build_content(source)

    def _build_content(self, source: str) -> None:
        root = FloatLayout()
        scatter = _PreviewScatter(
            on_tap=self.dismiss,
            do_rotation=False,
            do_scale=True,
            do_translation=True,
            scale_min=1.0,
            scale_max=5.0,
            size_hint=(None, None),
        )
        image = Image(source=source, fit_mode="contain", size_hint=(None, None))
        scatter.add_widget(image)
        root.add_widget(scatter)

        def _sync_image(*_args: object) -> None:
            if image.texture is None or image.texture.width <= 0:
                return
            available_width = max(dp(1), self.width - dp(32))
            available_height = max(dp(1), self.height - dp(32))
            ratio = min(
                available_width / image.texture.width,
                available_height / image.texture.height,
            )
            image.size = (
                image.texture.width * ratio,
                image.texture.height * ratio,
            )
            scatter.size = image.size
            scatter.pos = (
                (self.width - scatter.width) / 2,
                (self.height - scatter.height) / 2,
            )

        image.bind(texture=_sync_image)
        self.bind(size=_sync_image)
        _sync_image()
        self.add_widget(root)

@dataclass(frozen=True)
class TutorialBlock:
    """One controlled presentation element in the user tutorial."""

    kind: Literal["title", "heading", "subheading", "paragraph", "note", "list", "image"]
    text: str = ""
    image_filename: str | None = None


TUTORIAL_BLOCKS: tuple[TutorialBlock, ...] = (
    TutorialBlock("title", "ReversibleMosaic"),
    TutorialBlock(
        "paragraph",
        "ReversibleMosaic 是一款 Android 本地图片视觉混淆工具：选择一张图片，"
        "在手机上完成打码、保存和恢复。图片不需要上传到服务器，适合在分享前暂时遮挡照片中的文字、"
        "人物细节或其他不希望直接被看清的内容。",
    ),
    TutorialBlock(
        "note",
        "[b]重要说明[/b]\nReversibleMosaic 提供的是“可逆视觉混淆”，不是密码学加密。"
        "它不能保证绝对保密、身份认证或防止他人尝试猜测分享代码。",
    ),
    TutorialBlock("heading", "APP 使用效果"),
    TutorialBlock(
        "paragraph",
        "下面使用同一张原图展示不同打码轮次的效果。轮次越高，通常越难直接看清原图内容，"
        "但处理时间也可能相应增加。",
    ),
    TutorialBlock("image", "不同打码轮次的效果对比", "example_compare.png"),
    TutorialBlock(
        "list",
        "• [b]原图[/b]：未处理的图片。\n"
        "• [b]2 轮[/b]：适合快速确认流程，局部细节会被打乱，主体轮廓可能仍然可辨认。\n"
        "• [b]5 轮（默认）[/b]：文字和细节通常已经难以直接辨认。\n"
        "• [b]15 轮[/b]：更强的视觉混淆，适合对隐私要求更高的场景。\n"
        "• [b]30 轮[/b]：V1 提供的最高轮次。",
    ),
    TutorialBlock(
        "paragraph",
        "示意图只用于说明视觉变化，不代表任何密码学安全等级，也不表示所有图片在每个轮次下都能达到相同的遮挡效果。",
    ),
    TutorialBlock("heading", "快速开始"),
    TutorialBlock("subheading", "1. 从首页选择操作"),
    TutorialBlock("paragraph", "打开 ReversibleMosaic 后，会看到首页："),
    TutorialBlock("image", "APP 首页", "app-home.png"),
    TutorialBlock(
        "list",
        "• 选择 [b]图片打码[/b]，生成视觉混淆后的图片；\n"
        "• 选择 [b]图片恢复[/b]，恢复之前处理过的图片；\n"
        "• 选择 [b]教程 | 须知[/b]，查看应用内的使用说明和注意事项。",
    ),
    TutorialBlock("subheading", "2. 生成混淆图片"),
    TutorialBlock("paragraph", "在首页点击 [b]图片打码[/b]，然后按以下步骤操作："),
    TutorialBlock("image", "APP 打码页面", "app-encrypted.png"),
    TutorialBlock(
        "list",
        "1. 点击 [b]选择图片...[/b]，选择需要处理的图片；\n"
        "2. 选择打码轮次，默认使用 [b]5 轮[/b]；\n"
        "3. 分享代码会自动填入，通常不需要修改（默认值为 500000）。如需使用其他代码，可以自行修改，"
        "或点击 [b]随机 6 位[/b] 生成新代码；\n"
        "4. 点击 [b]开始打码[/b]；\n"
        "5. 处理完成后，预览结果并保存到手机，或使用 Android 系统分享功能。",
    ),
    TutorialBlock(
        "note",
        "需要将混淆图片交给他人恢复时，请通过你信任的渠道单独告知对方你修改后的分享代码，"
        "不要公开发布。",
    ),
    TutorialBlock(
        "paragraph",
        "当前支持 8-bit RGB/RGBA PNG、普通 8-bit RGB JPEG/JPG，以及手机拍摄的 JPEG 图片。"
        "APP 会先处理常见的照片方向信息。",
    ),
    TutorialBlock("subheading", "3. 恢复原图"),
    TutorialBlock("paragraph", "在首页点击 [b]图片恢复[/b]，选择之前生成的混淆图片："),
    TutorialBlock("image", "APP 恢复页面", "app-restored.png"),
    TutorialBlock(
        "list",
        "1. 点击 [b]选择图片...[/b]；\n"
        "2. 选择对应的算法版本（当前使用 V1）；\n"
        "3. 选择生成混淆图片时使用的轮次；\n"
        "4. APP 会自动使用 500000 作为分享代码，无需用户填入。只有打码时修改过代码，"
        "才需要输入完全相同的分享代码；\n"
        "5. 点击 [b]开始恢复[/b]。",
    ),
    TutorialBlock(
        "paragraph",
        "恢复时必须使用正确的算法版本、轮次和分享代码。参数正确时，恢复结果应与处理前的图片逐字节一致。"
        "如果混淆图片的元数据信息完好，APP 可以自动识别其中的算法版本和轮次信息，无需用户填写。",
    ),
    TutorialBlock("subheading", "4. 查看恢复结果"),
    TutorialBlock("paragraph", "恢复完成后，APP 会显示恢复出的图片："),
    TutorialBlock("image", "恢复成功后的页面", "after-restored.png"),
    TutorialBlock("paragraph", "确认结果无误后，可以将图片保存到手机，或使用系统分享功能。"),
    TutorialBlock("heading", "APP 功能"),
    TutorialBlock("subheading", "图片处理"),
    TutorialBlock(
        "list",
        "• 本地完成单张图片的混淆与恢复；\n"
        "• 支持 RGB 和 RGBA 图片；\n"
        "• PNG 结果使用无损格式保存；\n"
        "• RGBA 图片的透明度会随像素一起保留；\n"
        "• 可以保存结果并调用 Android 系统分享。",
    ),
    TutorialBlock("subheading", "自动读取算法版本和轮次信息"),
    TutorialBlock(
        "list",
        "• APP 可以自动识别打码时保存在图片元数据中的算法版本和轮次信息，并在恢复时自动填入；\n"
        "• 如果图片被社交媒体压缩或丢失元数据，则需要手动填写正确的算法版本和轮次信息；\n"
        "• 分享代码不会加入图片元数据中，只能由分享者通过可靠渠道发送给接收方。",
    ),
    TutorialBlock("subheading", "分享代码"),
    TutorialBlock(
        "paragraph",
        "分享代码用于让 APP 在打码和恢复时使用同一组处理参数：",
    ),
    TutorialBlock(
        "list",
        "• 打码和恢复页面都会自动填入分享代码（默认 500000），通常不需要手动填写；\n"
        "• 如需使用其他代码，可以手动修改，或点击 [b]随机 6 位[/b] 生成新代码；\n"
        "• 只有在打码时修改过代码，恢复时才需要把代码改回打码时使用的内容；\n"
        "• 需要让他人恢复图片时，请将混淆图片和对应的分享代码通过可信渠道交给对方，不要公开发布；\n"
        "• 如果丢失了分享代码，则可能无法恢复图片；\n"
        "• 分享代码不会写入结果图片的元数据、文件名、日志或系统分享文字。",
    ),
    TutorialBlock(
        "note",
        "分享代码只是恢复图片所需的处理参数，不是密码学意义上的安全口令。"
        "ReversibleMosaic 也不是密码学加密工具。",
    ),
    TutorialBlock("subheading", "隐私保护"),
    TutorialBlock(
        "list",
        "• 图片在本机处理，不依赖网络服务；\n"
        "• APP 不需要联网来完成核心处理；\n"
        "• 不建立图片历史记录；\n"
        "• 不保存最近使用的图片 URI 或分享代码；\n"
        "• 分享代码不会写入 PNG 元数据、文件名、日志或系统分享文字。",
    ),
    TutorialBlock("subheading", "可逆处理"),
    TutorialBlock(
        "paragraph",
        "ReversibleMosaic 不是把图片永久涂黑或裁剪掉，而是重新排列图片中的像素位置。"
        "使用正确的分享代码和轮次，可以把混淆图片恢复为原图。",
    ),
    TutorialBlock("heading", "使用限制与建议"),
    TutorialBlock(
        "list",
        "• 请保存好原图，尤其是在首次使用或处理重要图片时。\n"
        "• 恢复时必须使用正确的分享代码和轮次；缺少任一项都可能无法恢复。\n"
        "• 不建议把经过社交平台二次压缩、裁剪、滤镜处理或重新编码的图片用于恢复。"
        "JPEG 有损压缩可能改变像素，导致恢复结果不再完全一致。\n"
        "• 纯色图片、极小图片或本身细节很少的图片，视觉上可能看不出明显变化。\n"
        "• 视觉混淆不是绝对安全措施。对高敏感内容，请使用专业的加密工具，并通过安全渠道传输。",
    ),
    TutorialBlock("heading", "项目定位"),
    TutorialBlock(
        "paragraph",
        "ReversibleMosaic 的目标是提供一个简单、离线、可恢复的图片视觉混淆流程，"
        "而不是替代成熟的密码学加密、数字签名或防篡改方案。",
    ),
)


class TutorialScreen(Screen):  # type: ignore[misc]
    """A fixed-header, scrollable presentation of the user tutorial."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._build_widget_tree()

    def _build_widget_tree(self) -> None:
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        root.add_widget(
            Label(
                text="教程 | 须知",
                font_size=dp(24),
                bold=True,
                size_hint_y=None,
                height=dp(42),
                halign="left",
                valign="middle",
                text_size=(None, dp(42)),
            )
        )

        scroll = ScrollView(size_hint=(1, 1), bar_width=dp(5))
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
            padding=(dp(4), dp(4), dp(12), dp(20)),
        )
        content.bind(minimum_height=content.setter("height"))
        for block in TUTORIAL_BLOCKS:
            self._add_block(content, block)
        scroll.add_widget(content)
        root.add_widget(scroll)

        back_button = Button(text="返回首页", size_hint_y=None, height=dp(52))
        back_button.bind(on_release=lambda _button: self._go_home())
        root.add_widget(back_button)
        self.add_widget(root)

    def _add_block(self, parent: BoxLayout, block: TutorialBlock) -> None:
        if block.kind == "image":
            if block.image_filename is None:
                raise ValueError("image tutorial block requires an image filename")
            parent.add_widget(self._image_block(block.text, block.image_filename))
            return
        if block.kind == "note":
            parent.add_widget(self._note_block(block.text))
            return
        font_sizes = {
            "title": dp(28),
            "heading": dp(22),
            "subheading": dp(18),
            "paragraph": dp(16),
            "list": dp(16),
        }
        label = self._text_label(
            block.text,
            font_size=font_sizes[block.kind],
            bold=block.kind in {"title", "heading", "subheading"},
        )
        parent.add_widget(label)

    @staticmethod
    def _text_label(text: str, *, font_size: float, bold: bool = False) -> Label:
        label = Label(
            text=text,
            markup=True,
            font_size=font_size,
            bold=bold,
            size_hint_y=None,
            halign="left",
            valign="top",
        )
        label.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
        label.bind(texture_size=lambda widget, size: setattr(widget, "height", size[1]))
        return label

    def _note_block(self, text: str) -> BoxLayout:
        card = BoxLayout(
            padding=(dp(14), dp(12)),
            size_hint_y=None,
        )
        with card.canvas.before:
            Color(0.94, 0.96, 1, 1)
            background = RoundedRectangle(radius=[dp(12)])

        def _sync_background(*_args: object) -> None:
            background.pos = card.pos
            background.size = card.size

        card.bind(pos=_sync_background, size=_sync_background)
        label = self._text_label(text, font_size=dp(16))
        card.add_widget(label)
        label.bind(texture_size=lambda _widget, size: setattr(card, "height", size[1] + dp(24)))
        return card

    def _image_block(self, caption: str, filename: str) -> BoxLayout:
        wrapper = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        caption_label = self._text_label(caption, font_size=dp(14), bold=True)
        source = str(TUTORIAL_ASSET_DIR / filename)
        image = _TutorialImageButton(
            on_activate=lambda: self._show_image_preview(source),
            source=source,
            fit_mode="contain",
            size_hint_y=None,
        )
        hint_label = self._text_label(
            "轻触图片可放大预览",
            font_size=dp(13),
        )
        hint_label.color = (0.3, 0.3, 0.3, 1)
        wrapper.add_widget(caption_label)
        wrapper.add_widget(image)
        wrapper.add_widget(hint_label)

        def _sync_height(*_args: object) -> None:
            texture = image.texture
            if texture is None or texture.width <= 0:
                return
            image.height = image.width * texture.height / texture.width
            wrapper.height = caption_label.height + image.height + hint_label.height + dp(12)

        image.bind(width=_sync_height, texture=_sync_height)
        caption_label.bind(texture_size=_sync_height)
        hint_label.bind(texture_size=_sync_height)
        return wrapper

    def _show_image_preview(self, source: str) -> _TutorialImagePreview:
        preview = _TutorialImagePreview(source=source)
        preview.open()
        return preview

    def _go_home(self) -> None:
        if self.manager is not None:
            self.manager.current = "home"


__all__ = [
    "TUTORIAL_ASSET_DIR",
    "TUTORIAL_BLOCKS",
    "TUTORIAL_IMAGE_FILENAMES",
    "TutorialBlock",
    "TutorialScreen",
]
