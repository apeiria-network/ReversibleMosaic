"""Application shell wiring up ScreenManager, TaskCoordinator and adapters.

The app owns a single :class:`TaskCoordinator` that runs encode / decode work
off the UI thread. Screens read form state from ``app.encrypted_form_state``
and ``app.restored_form_state``; the coordinator's callbacks bounce results
back onto Kivy's main thread via ``Clock.schedule_once`` before touching any
widget.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from kivy.app import App
    from kivy.clock import Clock
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


# Import after font registration so all labels use wqy-microhei.
from reversible_mosaic.core.pipeline import PipelineResult  # noqa: E402
from reversible_mosaic.core.task_coordinator import TaskCoordinator, TaskRequest  # noqa: E402
from reversible_mosaic.domain.task_state import TaskState  # noqa: E402
from reversible_mosaic.ui.screens import (  # noqa: E402
    DecodeScreen,
    EncodeScreen,
    ProgressScreen,
    ResultScreen,
)
from reversible_mosaic.ui.self_test import SelfTestScreen  # noqa: E402
from reversible_mosaic.ui.view_models import (  # noqa: E402
    ProgressSnapshot,
    ResultSnapshot,
    TaskFormState,
)

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
            on_release: app.open_encode()
        Button:
            text: "恢复"
            size_hint_y: None
            height: dp(52)
            on_release: app.open_decode()
        Button:
            text: "教程与安全边界"
            size_hint_y: None
            height: dp(52)
            on_release: app.root.current = "tutorial"
        Button:
            text: "阶段 0 自检 (临时)"
            size_hint_y: None
            height: dp(40)
            font_size: dp(14)
            on_release: app.root.current = "self_test"

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

ScreenManager:
    HomeScreen:
    TutorialScreen:
    EncodeScreen:
        name: "encode"
    DecodeScreen:
        name: "decode"
    ProgressScreen:
        name: "progress"
    ResultScreen:
        name: "result"
    SelfTestScreen:
        name: "self_test"
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


# Re-export so KV Builder resolves the widget names.
__all__ = [
    "DecodeScreen",
    "EncodeScreen",
    "HomeScreen",
    "ProgressScreen",
    "ResultScreen",
    "ReversibleMosaicApp",
    "SelfTestScreen",
    "TutorialScreen",
]


class ReversibleMosaicApp(App):  # type: ignore[misc]
    """Root app that owns pipeline state and the worker-thread coordinator."""

    encrypted_form_state: TaskFormState
    restored_form_state: TaskFormState
    last_result: ResultSnapshot | None = None
    last_operation: str | None = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.encrypted_form_state = TaskFormState(operation="encrypted")
        self.restored_form_state = TaskFormState(operation="restored")
        self._coordinator: TaskCoordinator | None = None

    def build(self):  # type: ignore[no-untyped-def]
        return Builder.load_string(_KV)

    # -- navigation helpers --------------------------------------------------

    def open_encode(self) -> None:
        self.root.current = "encode"

    def open_decode(self) -> None:
        self.root.current = "decode"

    # -- task launch ---------------------------------------------------------

    def _coordinator_instance(self) -> TaskCoordinator:
        if self._coordinator is None:
            coordinator = TaskCoordinator(
                schedule_on_main=lambda callback: Clock.schedule_once(
                    lambda _dt: callback(), 0
                )
            )
            coordinator.on_progress = self._on_progress
            coordinator.on_completed = self._on_completed
            coordinator.on_failed = self._on_failed
            coordinator.on_cancelled = self._on_cancelled
            self._coordinator = coordinator
        return self._coordinator

    def launch_pipeline(self, operation: str, form: TaskFormState) -> None:
        if form.input_path is None:
            return
        try:
            share_code = form.parsed_share_code()
        except Exception:
            return
        output_dir = Path(self.user_data_dir) / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        from time import strftime

        prefix = "RM_ENC" if operation == "encrypted" else "RM_DEC"
        suffix = f"_R{form.rounds}" if operation == "encrypted" else ""
        output_path = output_dir / f"{prefix}_{strftime('%Y%m%d_%H%M%S')}{suffix}.png"

        request = TaskRequest(
            operation=operation,  # type: ignore[arg-type]
            input_path=form.input_path,
            output_path=output_path,
            rounds=form.rounds,
            share_code=share_code,
            algorithm_version=form.algorithm_version if operation == "restored" else None,
        )
        self.last_operation = operation
        self.last_result = None
        progress_screen = self._get_progress_screen()
        progress_screen.start_ticker()
        self.root.current = "progress"

        coordinator = self._coordinator_instance()
        if coordinator.state != TaskState.IDLE:
            coordinator.reset()
        coordinator.start(request)

    def cancel_pipeline(self) -> None:
        if self._coordinator is not None:
            self._coordinator.cancel()

    def copy_share_code_to_clipboard(self, share_code_line: str) -> None:
        """Best-effort clipboard copy — real sensitive-flagging comes later."""
        try:
            from kivy.core.clipboard import Clipboard

            Clipboard.copy(share_code_line)
        except Exception:
            return

    # -- coordinator callbacks (already scheduled on the main thread) -------

    def _on_progress(self, stage: str, fraction: float | None) -> None:
        snapshot = ProgressSnapshot.from_stage(stage, fraction)
        self._get_progress_screen().apply_progress(snapshot)

    def _on_completed(self, result: PipelineResult) -> None:
        snapshot = ResultSnapshot.from_pipeline(result)
        self.last_result = snapshot
        self._get_progress_screen().stop_ticker()
        self._get_result_screen().apply_result(snapshot)
        self.root.current = "result"
        if self._coordinator is not None:
            self._coordinator.reset()

    def _on_failed(self, exc: BaseException) -> None:
        self._get_progress_screen().stop_ticker()
        # Surface the error on the progress screen so the user can go back.
        self._get_progress_screen().stage_label = f"失败: {exc}"
        if self._coordinator is not None:
            self._coordinator.reset()

    def _on_cancelled(self) -> None:
        self._get_progress_screen().stop_ticker()
        self.root.current = "home"
        if self._coordinator is not None:
            self._coordinator.reset()

    # -- screen accessors ----------------------------------------------------

    def _get_progress_screen(self) -> ProgressScreen:
        return self.root.get_screen("progress")  # type: ignore[no-any-return]

    def _get_result_screen(self) -> ResultScreen:
        return self.root.get_screen("result")  # type: ignore[no-any-return]
