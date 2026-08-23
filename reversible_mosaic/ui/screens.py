"""Encode / decode / progress / result screens for the MVP UI.

All four screens live in one module so cross-screen callbacks stay close
together. Each screen builds its widget tree in ``__init__`` (programmatic UI
matches ``self_test.SelfTestScreen``'s pattern and dodges KV name-scoping
gotchas). The ``TaskCoordinator`` lives on :class:`ReversibleMosaicApp`; the
screens read/write shared state via ``app.form_state`` / ``app.last_result``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.graphics import Color, Line, RoundedRectangle
    from kivy.metrics import dp
    from kivy.properties import StringProperty
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.image import Image
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.progressbar import ProgressBar
    from kivy.uix.screenmanager import Screen
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
except ImportError as exc:  # pragma: no cover - matches app.py boundary
    raise RuntimeError("请安装 app 依赖后启动界面: pip install -e '.[app]'") from exc

from reversible_mosaic.core.algorithm.registry import supported_versions
from reversible_mosaic.domain.share_code import ShareCodeError
from reversible_mosaic.domain.task_state import TaskState
from reversible_mosaic.ui.file_picker import open_file_picker
from reversible_mosaic.ui.input_hint import InputHint, format_file_size, inspect_input
from reversible_mosaic.ui.view_models import (
    DEFAULT_ROUNDS,
    VALID_ROUNDS,
    ProgressSnapshot,
    ResultSnapshot,
    TaskFormState,
)

_ROUND_LABELS: tuple[str, ...] = tuple(f"{n} 轮" for n in VALID_ROUNDS)
_ROUND_FROM_LABEL: dict[str, int] = dict(zip(_ROUND_LABELS, VALID_ROUNDS, strict=True))


def _round_label(rounds: int) -> str:
    return f"{rounds} 轮"


def _spinner_style(spinner: Spinner) -> None:
    spinner.background_normal = ""
    spinner.background_down = ""
    spinner.background_color = (0, 0, 0, 1)
    spinner.color = (1, 1, 1, 1)
    spinner.border = (0, 0, 0, 0)


def _spinner_option_style(option: Button) -> None:
    option.background_normal = ""
    option.background_down = ""
    option.background_color = (0, 0, 0, 1)
    option.color = (1, 1, 1, 1)
    option.border = (0, 0, 0, 0)


def _result_button_style(button: Button) -> None:
    """Apply the white-panel action style without changing global buttons."""
    button.color = (0, 0, 0, 1)
    button.background_normal = ""
    button.background_down = ""
    button.background_disabled_normal = ""
    button.background_disabled_down = ""
    button.background_color = (0, 0, 0, 0)
    button.border = (0, 0, 0, 0)
    with button.canvas.before:
        fill_color = Color(1, 1, 1, 1)
        fill = RoundedRectangle(radius=[dp(8)])
        border_color = Color(0, 0, 0, 1)
        outline = Line(rounded_rectangle=(0, 0, 0, 0, dp(8)), width=dp(1))

    def _sync_style(*_args: Any) -> None:
        if button.disabled:
            fill_color.rgba = (0.9, 0.9, 0.9, 1)
            border_color.rgba = (0.55, 0.55, 0.55, 1)
            button.color = (0.45, 0.45, 0.45, 1)
        else:
            fill_color.rgba = (0.92, 0.92, 0.92, 1) if button.state == "down" else (1, 1, 1, 1)
            border_color.rgba = (0, 0, 0, 1)
            button.color = (0, 0, 0, 1)
        fill.pos = button.pos
        fill.size = button.size
        outline.rounded_rectangle = (*button.pos, *button.size, dp(8))

    button.bind(pos=_sync_style, size=_sync_style, state=_sync_style, disabled=_sync_style)
    _sync_style()


def _result_button(label: str) -> Button:
    button = Button(text=label)
    _result_button_style(button)
    return button


def _popup_style(popup: Popup) -> None:
    """Keep result-flow confirmation popups aligned with the white UI."""
    popup.background = ""
    popup.background_color = (1, 1, 1, 1)
    popup.title_color = (0, 0, 0, 1)
    popup.separator_color = (0, 0, 0, 1)


def _force_text_input_style(widget: TextInput) -> None:
    widget.foreground_color = (0, 0, 0, 1)
    widget.cursor_color = (0, 0, 0, 1)
    widget.selection_color = (0.75, 0.75, 0.75, 1)
    widget.background_color = (1, 1, 1, 1)
    widget.background_active = ""
    widget.background_normal = ""


def _label_row(text: str) -> Label:
    return Label(
        text=text,
        size_hint_y=None,
        height=dp(28),
        halign="left",
        valign="middle",
        text_size=(None, dp(28)),
    )


def _hint_lines(hint: InputHint) -> str:
    if not hint.is_ok:
        return f"无法预览: {hint.error}"
    lines = [
        f"文件: {hint.path.name}",
        f"格式: {hint.format}  规范化模式: {hint.mode}  {hint.width}x{hint.height}",
        f"大小: {format_file_size(hint.file_bytes)}",
    ]
    if hint.metadata.metadata is not None:
        meta = hint.metadata.metadata
        lines.append(
            f"元数据: op={meta.operation_type}, 算法 V{meta.algorithm_version}, {meta.rounds} 轮"
        )
    elif hint.metadata.reason:
        lines.append(f"元数据: 异常 ({hint.metadata.reason})")
    else:
        lines.append("元数据: 无 (可能不是本 App 输出)")
    return "\n".join(lines)


class _BlackTextInput(TextInput):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        _force_text_input_style(self)

    def on_foreground_color(self, *_args: Any) -> None:
        _force_text_input_style(self)

    def on_background_color(self, *_args: Any) -> None:
        _force_text_input_style(self)


class _EncodeDecodeBase(Screen):  # type: ignore[misc]
    """Shared UI parts for encode and decode screens."""

    operation: str = "encrypted"
    header_text: str = "打码"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._hint: InputHint | None = None
        self._rounds_spinner: Spinner
        self._share_code_input: TextInput
        self._preview_label: Label
        self._start_button: Button
        self._error_label: Label
        self._build_widget_tree()

    def _build_widget_tree(self) -> None:
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        title = Label(
            text=self.header_text,
            font_size=dp(22),
            size_hint_y=None,
            height=dp(40),
        )
        root.add_widget(title)

        pick_button = Button(
            text="选择图片…",
            size_hint_y=None,
            height=dp(48),
        )
        pick_button.bind(on_release=lambda _btn: self._on_pick())
        root.add_widget(pick_button)

        self._preview_label = Label(
            text="尚未选择图片。",
            size_hint_y=None,
            height=dp(96),
            halign="left",
            valign="top",
            text_size=(None, dp(96)),
        )
        root.add_widget(self._preview_label)

        self._append_operation_specific(root)

        root.add_widget(_label_row("轮数（轮数越多，打码效果越好）"))
        self._rounds_spinner = Spinner(
            text=_round_label(DEFAULT_ROUNDS),
            values=_ROUND_LABELS,
            size_hint_y=None,
            height=dp(44),
        )
        _spinner_style(self._rounds_spinner)
        self._rounds_spinner.bind(text=lambda _s, _val: self._sync_form())
        root.add_widget(self._rounds_spinner)

        root.add_widget(_label_row("分享代码 (留空使用默认 500000)"))
        self._share_code_input = _BlackTextInput(
            text="",
            multiline=False,
            font_size=dp(18),
            size_hint_y=None,
            height=dp(44),
            hint_text="1-10 位十进制数字",
        )
        self._share_code_input.bind(text=lambda _t, _val: self._sync_form())
        root.add_widget(self._share_code_input)

        code_actions = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(6)
        )
        if self.operation == "encrypted":
            code_actions.add_widget(
                _mini_button("随机 6 位", lambda: self._on_randomize_share_code())
            )
            code_actions.add_widget(_mini_button("清除", lambda: self._on_clear_share_code()))
        else:
            clear_button = _mini_button("清除", lambda: self._on_clear_share_code())
            clear_button.size_hint_x = 2
            code_actions.add_widget(clear_button)
        root.add_widget(code_actions)

        self._error_label = Label(
            text="",
            color=(1, 0.4, 0.4, 1),
            size_hint_y=None,
            height=dp(28),
            halign="left",
            valign="middle",
            text_size=(None, dp(28)),
        )
        root.add_widget(self._error_label)

        actions = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(56), spacing=dp(12)
        )
        back_btn = Button(text="返回首页")
        back_btn.bind(on_release=lambda _btn: self._go_home())
        self._start_button = Button(text=self._start_button_label(), disabled=True)
        self._start_button.bind(on_release=lambda _btn: self._on_start())
        actions.add_widget(back_btn)
        actions.add_widget(self._start_button)
        root.add_widget(actions)

        self.add_widget(root)

    def _append_operation_specific(self, root: BoxLayout) -> None:
        """Encode has no extra fields; decode overrides for version dropdown."""

    def _start_button_label(self) -> str:
        return "开始打码"

    def _current_form(self) -> TaskFormState:
        app = App.get_running_app()
        form = getattr(app, f"{self.operation}_form_state")
        assert isinstance(form, TaskFormState)
        return form

    def _on_pre_enter(self, *_args: Any) -> None:
        self._refresh_from_form()

    def on_pre_enter(self, *args: Any) -> None:
        self._on_pre_enter(*args)

    def _refresh_from_form(self) -> None:
        form = self._current_form()
        if form.input_path is not None:
            self._hint = inspect_input(form.input_path)
            self._preview_label.text = _hint_lines(self._hint)
        else:
            self._hint = None
            self._preview_label.text = "尚未选择图片。"
        self._rounds_spinner.text = _round_label(form.rounds)
        self._share_code_input.text = form.share_code
        self._update_start_state()

    def _sync_form(self) -> None:
        form = self._current_form()
        selected = _ROUND_FROM_LABEL.get(self._rounds_spinner.text, DEFAULT_ROUNDS)
        form.rounds = selected
        form.share_code = self._share_code_input.text
        self._update_start_state()

    def _update_start_state(self) -> None:
        form = self._current_form()
        error_text = ""
        can_start = form.can_start()
        if form.input_path is None:
            error_text = "请先选择图片。"
            can_start = False
        elif self._hint is not None and not self._hint.is_ok:
            error_text = f"图片无法处理: {self._hint.error}"
            can_start = False
        else:
            try:
                form.parsed_share_code()
            except ShareCodeError as exc:
                error_text = str(exc)
                can_start = False
        self._error_label.text = error_text
        self._start_button.disabled = not can_start

    def _on_pick(self) -> None:
        def _cb(chosen: Path, display_name: str | None) -> None:
            form = self._current_form()
            form.input_path = chosen
            form.original_display_name = display_name
            self._hint = inspect_input(chosen)
            self._preview_label.text = _hint_lines(self._hint)
            self._on_input_selected(self._hint)
            self._update_start_state()

        open_file_picker(_cb)

    def _on_input_selected(self, _hint: InputHint) -> None:
        """Overridden by decode screen to auto-populate rounds / version."""

    def _on_randomize_share_code(self) -> None:
        form = self._current_form()
        form.randomize_share_code()
        self._share_code_input.text = form.share_code
        self._update_start_state()

    def _on_clear_share_code(self) -> None:
        self._share_code_input.text = ""
        self._sync_form()

    def _on_start(self) -> None:
        form = self._current_form()
        if not form.can_start():
            return
        app = App.get_running_app()
        app.launch_pipeline(self.operation, form)

    def _go_home(self) -> None:
        if self.manager is not None:
            self.manager.current = "home"


def _mini_button(label: str, callback: Callable[[], None]) -> Button:
    button = Button(text=label, size_hint_y=None, height=dp(40))
    button.bind(on_release=lambda _btn: callback())
    return button


class EncodeScreen(_EncodeDecodeBase):
    operation = "encrypted"
    header_text = "打码"


class DecodeScreen(_EncodeDecodeBase):
    operation = "restored"
    header_text = "恢复"

    def _start_button_label(self) -> str:
        return "开始恢复"

    def _append_operation_specific(self, root: BoxLayout) -> None:
        root.add_widget(_label_row("算法版本"))
        options = [
            f"V{descriptor.version} ({descriptor.display_name})"
            for descriptor in supported_versions()
        ]
        if not options:
            options = ["V1 (2026-8-22)"]
        self._version_spinner = Spinner(
            text=options[0],
            values=options,
            size_hint_y=None,
            height=dp(44),
        )
        self._version_spinner.bind(text=lambda _s, _val: self._sync_version_form())
        root.add_widget(self._version_spinner)
        self._version_options = options

    def _sync_version_form(self) -> None:
        form = self._current_form()
        version_text = self._version_spinner.text
        try:
            version_number = int(version_text.split()[0][1:])
        except (ValueError, IndexError):
            version_number = 1
        form.algorithm_version = version_number
        self._sync_form()

    def _on_input_selected(self, hint: InputHint) -> None:
        form = self._current_form()
        if hint.suggested_rounds is not None and hint.suggested_rounds in VALID_ROUNDS:
            form.rounds = hint.suggested_rounds
            self._rounds_spinner.text = _round_label(form.rounds)
        if hint.suggested_algorithm_version is not None:
            target = f"V{hint.suggested_algorithm_version} "
            for option in self._version_options:
                if option.startswith(target):
                    self._version_spinner.text = option
                    break


class ProgressScreen(Screen):  # type: ignore[misc]
    """Screen shown while :class:`TaskCoordinator` is running."""

    stage_label = StringProperty("等待")
    detail_label = StringProperty("")
    elapsed_label = StringProperty("")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._start_time = 0.0
        self._tick_event = None
        self._build_widget_tree()

    def _build_widget_tree(self) -> None:
        root = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(16))
        root.add_widget(Label(text="正在处理", font_size=dp(22), size_hint_y=None, height=dp(48)))

        self._stage = Label(
            text=self.stage_label, font_size=dp(18), size_hint_y=None, height=dp(36)
        )
        root.add_widget(self._stage)

        self._detail = Label(
            text=self.detail_label,
            size_hint_y=None,
            height=dp(72),
            halign="left",
            valign="top",
            text_size=(None, dp(72)),
        )
        root.add_widget(self._detail)

        self._bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(20))
        root.add_widget(self._bar)

        self._elapsed = Label(
            text=self.elapsed_label, size_hint_y=None, height=dp(28)
        )
        root.add_widget(self._elapsed)

        root.add_widget(Label())  # spacer

        cancel_btn = Button(text="取消", size_hint_y=None, height=dp(56))
        cancel_btn.bind(on_release=lambda _btn: self._on_cancel())
        root.add_widget(cancel_btn)

        # Reactive: any assignment to `self.stage_label` / `detail_label` /
        # `elapsed_label` now updates the visible widget. Without this, code
        # paths like ReversibleMosaicApp._on_failed silently updated the
        # StringProperty but the label kept showing stale text.
        self.bind(stage_label=lambda _self, val: setattr(self._stage, "text", val))
        self.bind(detail_label=lambda _self, val: setattr(self._detail, "text", val))
        self.bind(elapsed_label=lambda _self, val: setattr(self._elapsed, "text", val))

        self.add_widget(root)

    def start_ticker(self) -> None:
        self._start_time = time.time()
        self.stage_label = "等待"
        self.detail_label = ""
        self._bar.value = 0
        if self._tick_event is None:
            self._tick_event = Clock.schedule_interval(self._tick, 0.1)

    def stop_ticker(self) -> None:
        if self._tick_event is not None:
            self._tick_event.cancel()
            self._tick_event = None

    def _tick(self, _dt: float) -> None:
        elapsed = time.time() - self._start_time
        self.elapsed_label = f"已耗时 {elapsed:.1f}s"

    def apply_progress(self, snapshot: ProgressSnapshot) -> None:
        self.stage_label = snapshot.label
        if snapshot.fraction is None:
            self._bar.value = 0
            self._bar.max = 0  # indeterminate look
            self._bar.max = 100
        else:
            self._bar.value = min(100, max(0, int(snapshot.fraction * 100)))

    def _on_cancel(self) -> None:
        app = App.get_running_app()
        # If the pipeline already finished (or failed) the coordinator is
        # IDLE; there is nothing to cancel and the user just wants to leave
        # the screen. Fall through to home so a failed run isn't a dead-end.
        coordinator = getattr(app, "_coordinator", None)
        if coordinator is None or coordinator.state == TaskState.IDLE:
            if self.manager is not None:
                self.manager.current = "home"
            return
        app.cancel_pipeline()

    def on_pre_leave(self, *_args: Any) -> None:
        self.stop_ticker()


class ResultScreen(Screen):  # type: ignore[misc]
    """Screen shown after a successful encode or decode.

    State machine:

    * ``unsaved`` — pipeline just finished, output lives only in app-private
      cache. The **Save** button is the only enabled destructive action.
      **View** is disabled because there is no gallery URI yet.
      **返回首页** goes through :meth:`on_pre_leave` to prompt about data
      loss (FR-SAVE-007).
    * ``saved`` — MediaStore publish succeeded. **View** unlocks;
      **Save** flips to "已保存"; leaving the screen no longer prompts.
    * ``save_error`` — surfaced above the buttons; user can retry Save.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._image_widget: Image | None = None
        self._summary_label: Label
        self._share_code_label: Label
        self._save_status_label: Label
        self._save_button: Button
        self._view_button: Button
        self._back_button: Button
        self._current_snapshot: ResultSnapshot | None = None
        self._build_widget_tree()

    def _build_widget_tree(self) -> None:
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        root.add_widget(Label(text="处理完成", font_size=dp(22), size_hint_y=None, height=dp(40)))

        self._image_widget = Image(size_hint=(1, 1), fit_mode="contain")
        root.add_widget(self._image_widget)

        self._summary_label = Label(
            text="",
            size_hint_y=None,
            height=dp(96),
            halign="left",
            valign="top",
            text_size=(None, dp(96)),
        )
        root.add_widget(self._summary_label)

        self._share_code_label = Label(
            text="",
            size_hint_y=None,
            height=dp(40),
            font_size=dp(18),
            halign="center",
            valign="middle",
            text_size=(None, dp(40)),
        )
        root.add_widget(self._share_code_label)

        self._save_status_label = Label(
            text="",
            size_hint_y=None,
            height=dp(28),
            font_size=dp(14),
            halign="center",
            valign="middle",
            text_size=(None, dp(28)),
        )
        root.add_widget(self._save_status_label)

        primary_actions = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8)
        )
        self._save_button = _result_button("保存到相册")
        self._save_button.bind(on_release=lambda _btn: self._on_save())
        self._view_button = _result_button("查看")
        self._view_button.disabled = True
        self._view_button.bind(on_release=lambda _btn: self._on_view())
        primary_actions.add_widget(self._save_button)
        primary_actions.add_widget(self._view_button)
        root.add_widget(primary_actions)

        secondary_actions = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8)
        )
        copy_btn = _result_button("复制分享代码")
        copy_btn.bind(on_release=lambda _btn: self._on_copy_share_code())
        self._back_button = _result_button("返回首页")
        self._back_button.bind(on_release=lambda _btn: self._on_back())
        secondary_actions.add_widget(copy_btn)
        secondary_actions.add_widget(self._back_button)
        root.add_widget(secondary_actions)

        self.add_widget(root)

    def apply_result(self, snapshot: ResultSnapshot) -> None:
        assert self._image_widget is not None
        self._current_snapshot = snapshot
        self._image_widget.source = str(snapshot.output_path)
        self._image_widget.reload()
        self._summary_label.text = (
            f"输出文件名: {snapshot.display_name or snapshot.output_path.name}\n"
            f"缓存路径: {snapshot.output_path}\n"
            f"算法: V{snapshot.algorithm_version}  轮数: {snapshot.rounds}"
        )
        # Only encode outputs surface the share code — decode reuses the same
        # value entered on the form so the user already has it.
        if snapshot.operation == "encrypted":
            self._share_code_label.text = f"分享代码: {snapshot.share_code_display}"
        else:
            self._share_code_label.text = ""
        self._refresh_save_state()

    def refresh_from_app(self) -> None:
        """Re-read ``app.last_result`` and update button states.

        Called by the app after a save succeeds / fails so the screen doesn't
        need to hold its own copy of the snapshot in sync.
        """
        app = App.get_running_app()
        if app is None:
            return
        snapshot = getattr(app, "last_result", None)
        if snapshot is None:
            return
        self._current_snapshot = snapshot
        self._refresh_save_state()

    def show_action_error(self, message: str) -> None:
        """Display a view/share error message on the status label.

        Bypasses ``_refresh_save_state``'s copy so a transient JNI error stays
        readable until the user takes another action (e.g. reruns save).
        """
        self._save_status_label.text = message

    def _refresh_save_state(self) -> None:
        snapshot = self._current_snapshot
        if snapshot is None:
            self._save_button.disabled = True
            self._view_button.disabled = True
            return
        if snapshot.is_saved:
            self._save_button.text = "已保存"
            self._save_button.disabled = True
            self._view_button.disabled = False
            self._save_status_label.text = "已保存至相册的 Pictures/ReversibleMosaic 目录。"
        else:
            self._save_button.text = "保存到相册"
            self._save_button.disabled = False
            self._view_button.disabled = True
            if snapshot.save_error:
                self._save_status_label.text = f"上次保存失败: {snapshot.save_error}"
            else:
                self._save_status_label.text = "尚未保存, 离开此页可能丢失结果。"

    # -- button handlers ----------------------------------------------------

    def _on_save(self) -> None:
        app = App.get_running_app()
        if app is None or self._current_snapshot is None:
            return
        self._save_status_label.text = "正在保存到相册..."
        self._save_button.disabled = True
        # Route through the app so the platform gateway lookup + callback
        # scheduling live in one place.
        if hasattr(app, "save_current_result"):
            app.save_current_result()

    def _on_view(self) -> None:
        app = App.get_running_app()
        if app is None:
            return
        if hasattr(app, "view_current_result"):
            app.view_current_result()

    def _on_copy_share_code(self) -> None:
        app = App.get_running_app()
        if app is None:
            return
        if not hasattr(app, "copy_share_code_to_clipboard"):
            return
        snapshot = self._current_snapshot
        if snapshot is None or snapshot.operation != "encrypted":
            return
        copied = bool(app.copy_share_code_to_clipboard(snapshot.share_code_display))
        if copied:
            self._save_status_label.text = "已复制到剪贴板 (其他软件可能读取剪贴板,请及时清除)。"
        else:
            self._save_status_label.text = "复制失败，请检查系统剪贴板后重试。"

    def _on_back(self) -> None:
        snapshot = self._current_snapshot
        if snapshot is not None and not snapshot.is_saved:
            self._show_unsaved_confirmation()
            return
        self._go_home()

    def _show_unsaved_confirmation(self) -> None:
        """FR-SAVE-007 unsaved-leave prompt."""
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        content.add_widget(
            Label(
                text=(
                    "当前结果尚未保存到相册,\n"
                    "离开后结果可能丢失。\n"
                    "确认离开?"
                ),
                halign="center",
                valign="middle",
            )
        )
        buttons = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8)
        )
        cancel = _result_button("继续保存")
        proceed = _result_button("仍然离开")
        buttons.add_widget(cancel)
        buttons.add_widget(proceed)
        content.add_widget(buttons)
        popup = Popup(
            title="尚未保存",
            content=content,
            size_hint=(0.85, 0.5),
            auto_dismiss=False,
        )
        _popup_style(popup)
        cancel.bind(on_release=lambda _btn: popup.dismiss())

        def _confirm(_btn: Button) -> None:
            popup.dismiss()
            self._go_home()

        proceed.bind(on_release=_confirm)
        popup.open()

    def _go_home(self) -> None:
        if self.manager is not None:
            self.manager.current = "home"
