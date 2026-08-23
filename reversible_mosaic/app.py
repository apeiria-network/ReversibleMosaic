"""Application shell wiring up ScreenManager, TaskCoordinator and adapters.

The app owns a single :class:`TaskCoordinator` that runs encode / decode work
off the UI thread. Screens read form state from ``app.encrypted_form_state``
and ``app.restored_form_state``; the coordinator's callbacks bounce results
back onto Kivy's main thread via ``Clock.schedule_once`` before touching any
widget.

Stage 2b adds platform gateways for the result page:

- :class:`AndroidOutputGateway` (or :class:`DesktopOutputGateway` on PC)
  publishes the finished cache PNG to the system gallery on user press.
- :class:`AndroidClipboardGateway` (or :class:`DesktopClipboardGateway`) copies
  the share code and flags the clip sensitive on Android 13+.
- Result naming: ``<original_stem>_mosaic.png`` for encode,
  ``<original_stem>_reversal_mosaic.png`` for decode, with ``_1/_2`` on
  collision (both in the cache dir and MediaStore).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

try:
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.text import LabelBase
    from kivy.core.window import Window
    from kivy.lang import Builder
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
from reversible_mosaic.domain.output_naming import compute_output_name  # noqa: E402
from reversible_mosaic.domain.task_state import TaskState  # noqa: E402
from reversible_mosaic.ui.screens import (  # noqa: E402
    DecodeScreen,
    EncodeScreen,
    ProgressScreen,
    ResultScreen,
)
from reversible_mosaic.ui.tutorial import TutorialScreen  # noqa: E402

try:
    from reversible_mosaic._build_info import SHOW_STAGE0_SELF_TEST
except ImportError:
    # Desktop development and source checkouts default to the diagnostic screen.
    SHOW_STAGE0_SELF_TEST = True

if SHOW_STAGE0_SELF_TEST:
    from reversible_mosaic.ui.self_test import SelfTestScreen  # noqa: F401

from reversible_mosaic.ui.view_models import (  # noqa: E402
    ProgressSnapshot,
    ResultSnapshot,
    TaskFormState,
)

Window.clearcolor = (1, 1, 1, 1)

_KV = r"""
#:import dp kivy.metrics.dp

<Label>:
    color: 0, 0, 0, 1

<Button>:
    color: 1, 1, 1, 1
    background_normal: ""
    background_down: ""
    background_disabled_normal: ""
    background_disabled_down: ""
    background_color: 0, 0, 0, 0
    border: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: (0, 0, 0, 1) if not self.disabled else (0.65, 0.65, 0.65, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

<Spinner>:
    color: 1, 1, 1, 1
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 1
    canvas.after:
        Color:
            rgba: 1, 1, 1, 1
        Triangle:
            points: [self.right - dp(20), self.center_y + dp(4), self.right - dp(10), self.center_y + dp(4), self.right - dp(15), self.center_y - dp(4)]

<SpinnerOption>:
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 1
    color: 1, 1, 1, 1
    border: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: 0, 0, 0, 1
        Rectangle:
            pos: self.pos
            size: self.size

<TextInput>:
    foreground_color: 0, 0, 0, 1
    hint_text_color: 0.45, 0.45, 0.45, 1
    background_normal: ""
    background_active: ""
    background_color: 1, 1, 1, 1
    cursor_color: 0, 0, 0, 1
    selection_color: 0.75, 0.75, 0.75, 1
    padding: dp(10), dp(8)
    canvas.before:
        Color:
            rgba: 0, 0, 0, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.x + dp(1), self.y + dp(1)
            size: self.width - dp(2), self.height - dp(2)
            radius: [dp(7)]
        Color:
            rgba: self.disabled_foreground_color if self.disabled else (self.hint_text_color if not self.text else self.foreground_color)


<HomeScreen>:
    name: "home"
    BoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(14)
        Label:
            text: "ReversibleMosaic"
            font_size: dp(28)
            size_hint_y: None
            height: dp(56)
            halign: "center"
            valign: "middle"
            text_size: self.size
        Widget:
            size_hint_y: 0.618
        AnchorLayout:
            size_hint_y: None
            height: dp(54)
            anchor_x: "center"
            anchor_y: "center"
            Button:
                text: "图片打码"
                size_hint_x: 0.82
                size_hint_y: None
                height: dp(54)
                on_release: app.open_encode()
        AnchorLayout:
            size_hint_y: None
            height: dp(54)
            anchor_x: "center"
            anchor_y: "center"
            Button:
                text: "图片恢复"
                size_hint_x: 0.82
                size_hint_y: None
                height: dp(54)
                on_release: app.open_decode()
        AnchorLayout:
            size_hint_y: None
            height: dp(54)
            anchor_x: "center"
            anchor_y: "center"
            Button:
                text: "教程|须知"
                size_hint_x: 0.82
                size_hint_y: None
                height: dp(54)
                on_release: app.root.current = "tutorial"
        Widget:
            size_hint_y: 0.30
        {self_test_button}

<TutorialScreen>:
    name: "tutorial"

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
{self_test_screen}
""".format(
    self_test_button=(
        'Button:\n'
        '            text: "阶段 0 自检 (临时)"\n'
        '            size_hint_y: None\n'
        '            height: dp(40)\n'
        '            font_size: dp(14)\n'
        '            on_release: app.root.current = "self_test"\n'
        if SHOW_STAGE0_SELF_TEST
        else ""
    ),
    self_test_screen=(
        '    SelfTestScreen:\n'
        '        name: "self_test"\n'
        if SHOW_STAGE0_SELF_TEST
        else ""
    ),
)




class HomeScreen(Screen):  # type: ignore[misc]
    pass


# Re-export so KV Builder resolves the widget names.
__all__ = [
    "DecodeScreen",
    "EncodeScreen",
    "HomeScreen",
    "ProgressScreen",
    "ResultScreen",
    "ReversibleMosaicApp",
    "TutorialScreen",
]

if SHOW_STAGE0_SELF_TEST:
    __all__.append("SelfTestScreen")


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
        self._output_gateway: Any = None
        self._clipboard_gateway: Any = None

    def build(self):  # type: ignore[no-untyped-def]
        return Builder.load_string(_KV)

    def on_start(self) -> None:
        """Kivy lifecycle hook — runs once the ScreenManager is live."""
        gateway = self._output_gateway_instance()
        cleanup = getattr(gateway, "cleanup_orphan_pending", None)
        if callable(cleanup):
            try:
                cleanup()
            except Exception:
                # Startup housekeeping must never crash the app.
                pass

    # -- navigation helpers --------------------------------------------------

    def open_encode(self) -> None:
        self.root.current = "encode"

    def open_decode(self) -> None:
        self.root.current = "decode"

    # -- gateways ------------------------------------------------------------

    def _output_gateway_instance(self) -> Any:
        if self._output_gateway is None:
            self._output_gateway = _build_output_gateway(Path(self.user_data_dir))
        return self._output_gateway

    def _clipboard_gateway_instance(self) -> Any:
        if self._clipboard_gateway is None:
            self._clipboard_gateway = _build_clipboard_gateway()
        return self._clipboard_gateway

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

        # Build cache filename from the ORIGINAL display name (Photo Picker /
        # PC path.name), not the picker's random ``pick_<ts>.jpg`` cache stem.
        # MediaStore save later reuses the same base name.
        display_name = compute_output_name(
            form.original_display_name,
            operation=operation,
            name_taken=lambda name: (output_dir / name).exists(),
        )
        output_path = output_dir / display_name

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

    def copy_share_code_to_clipboard(self, share_code_line: str) -> bool:
        """Copy ``share_code_line`` via the platform clipboard gateway.

        On Android 13+ the ``ClipDescription`` is flagged sensitive so the
        system UI redacts it in the copy-preview toast (FR-ENC-007).
        """
        try:
            gateway = self._clipboard_gateway_instance()
            return bool(gateway.copy_sensitive(share_code_line))
        except Exception:
            # Clipboard is decorative; never crash the flow.
            return False

    # -- coordinator callbacks (already scheduled on the main thread) -------

    def _on_progress(self, stage: str, fraction: float | None) -> None:
        snapshot = ProgressSnapshot.from_stage(stage, fraction)
        self._get_progress_screen().apply_progress(snapshot)

    def _on_completed(self, result: PipelineResult) -> None:
        snapshot = ResultSnapshot.from_pipeline(
            result,
            operation=self.last_operation or "encrypted",
            display_name=result.output_path.name,
        )
        self.last_result = snapshot
        self._get_progress_screen().stop_ticker()
        self._get_result_screen().apply_result(snapshot)
        self.root.current = "result"
        if self._coordinator is not None:
            self._coordinator.reset()

    def _on_failed(self, exc: BaseException) -> None:
        print(f"[RM] pipeline failed: {type(exc).__name__}")
        screen = self._get_progress_screen()
        screen.stop_ticker()
        screen.stage_label = "处理失败"
        screen.detail_label = "图片处理失败, 请检查图片和参数后重试。"
        if self._coordinator is not None:
            self._coordinator.reset()

    def _on_cancelled(self) -> None:
        self._get_progress_screen().stop_ticker()
        self.root.current = "home"
        if self._coordinator is not None:
            self._coordinator.reset()

    # -- result page actions ------------------------------------------------

    def save_current_result(self) -> None:
        """Publish the cached PNG to the platform gallery, off the UI thread."""
        snapshot = self.last_result
        if snapshot is None or snapshot.is_saved:
            return
        gateway = self._output_gateway_instance()
        source_path = snapshot.output_path
        display_name = snapshot.display_name or source_path.name

        def _work() -> None:
            try:
                handle = gateway.publish_png(source_path, display_name)
                Clock.schedule_once(lambda _dt: self._on_saved(handle), 0)
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__
                Clock.schedule_once(lambda _dt: self._on_save_failed(message), 0)

        threading.Thread(target=_work, name="rm-save", daemon=True).start()

    def view_current_result(self) -> None:
        snapshot = self.last_result
        if snapshot is None or not snapshot.is_saved or snapshot.saved_handle is None:
            return
        gateway = self._output_gateway_instance()
        try:
            gateway.open_for_view(snapshot.saved_handle)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self._get_result_screen().show_action_error(f"查看失败: {message}")

    def _on_saved(self, handle: str) -> None:
        snapshot = self.last_result
        if snapshot is None:
            return
        snapshot.saved_handle = handle
        snapshot.save_error = None
        self._get_result_screen().refresh_from_app()

    def _on_save_failed(self, message: str) -> None:
        snapshot = self.last_result
        if snapshot is None:
            return
        snapshot.saved_handle = None
        snapshot.save_error = message
        self._get_result_screen().refresh_from_app()

    # -- screen accessors ----------------------------------------------------

    def _get_progress_screen(self) -> ProgressScreen:
        return self.root.get_screen("progress")  # type: ignore[no-any-return]

    def _get_result_screen(self) -> ResultScreen:
        return self.root.get_screen("result")  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Gateway selection — Android when PyJNIus is present, desktop stubs otherwise.
# ---------------------------------------------------------------------------


def _build_output_gateway(user_data_dir: Path) -> Any:
    """Return an :class:`OutputGateway` implementation for the current platform."""
    try:
        from reversible_mosaic.android.native import (
            AndroidOutputGateway,
            is_available,
        )

        if is_available():
            return AndroidOutputGateway()
    except Exception:
        # Fall through to desktop stub — never let gateway construction crash
        # the app.
        pass
    from reversible_mosaic.android.desktop import DesktopOutputGateway

    return DesktopOutputGateway(user_data_dir / "gallery")


def _build_clipboard_gateway() -> Any:
    try:
        from reversible_mosaic.android.native import (
            AndroidClipboardGateway,
            is_available,
        )

        if is_available():
            return AndroidClipboardGateway()
    except Exception:
        pass
    # PC fallback: try Kivy's Clipboard for developer convenience so we can
    # still verify the copy flow on desktop.
    return _DesktopKivyClipboardGateway()


class _DesktopKivyClipboardGateway:
    """PC developer aid — copies text via Kivy's clipboard backend."""

    def copy_sensitive(self, text: str) -> bool:
        try:
            from kivy.core.clipboard import Clipboard

            Clipboard.copy(text)
            return True
        except Exception:
            return False
