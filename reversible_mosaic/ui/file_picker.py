"""Modal file picker for encode/decode screens.

Two implementations behind one interface:

- **Android** (``jnius`` importable): fires an ``Intent.ACTION_GET_CONTENT``
  chooser with the ``image/*`` MIME type. This is the system Photo Picker
  (Android 13+) or the classic doc-chooser (Android 8-12) — the OS decides.
  The picked ``content://`` URI is streamed into the app-private cache and
  the resulting file path is delivered to the callback on the UI thread.
- **PC / any non-Android platform**: Kivy's built-in ``FileChooserListView``
  inside a modal ``Popup``. Simple filesystem browsing keyed off the user's
  home directory. Not pretty but portable, useful for dev / desktop demo.

The screens call :func:`open_file_picker` and do not care which
implementation runs. ``on_selected(Path)`` fires exactly once per successful
pick; user cancel silently no-ops.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.filechooser import FileChooserListView
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("请安装 app 依赖后启动界面: pip install -e '.[app]'") from exc

try:
    from jnius import autoclass  # type: ignore[import-not-found]

    _HAS_JNIUS = True
except ImportError:
    _HAS_JNIUS = False


SelectionCallback = Callable[[Path], None]

_SUPPORTED_FILTERS = ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG")
_ANDROID_PICKER_REQUEST_CODE = 8901
_MAX_URI_COPY_BYTES = 100 * 1024 * 1024  # cap Photo Picker imports at 100 MiB


def open_file_picker(on_selected: SelectionCallback) -> Any:
    """Dispatch to the platform-appropriate picker."""
    if _HAS_JNIUS:
        try:
            return _open_android_gallery(on_selected)
        except Exception as exc:
            import traceback

            # Log to app private data dir so we can retrieve the traceback via
            # the self-test screen's file browser if a crash reappears.
            try:
                app = App.get_running_app()
                if app is not None:
                    log_path = Path(app.user_data_dir) / "picker_error.log"
                    with log_path.open("a", encoding="utf-8") as log:
                        log.write("--- picker error ---\n")
                        log.write(traceback.format_exc())
                        log.write("\n")
            except Exception:
                pass
            print(f"[file_picker] Android picker failed, falling back: {exc}")
            traceback.print_exc()
            return _open_kivy_filechooser(on_selected)
    return _open_kivy_filechooser(on_selected)


# ---------------------------------------------------------------------------
# Android: system Photo Picker / doc chooser
# ---------------------------------------------------------------------------


def _open_android_gallery(on_selected: SelectionCallback) -> None:
    """Launch the system image chooser via ``Intent.ACTION_GET_CONTENT``.

    On Android 13+ this surfaces the Photo Picker; older releases fall back
    to the document chooser. Result URI is streamed into the app-private
    cache before delivering the local path to ``on_selected``.
    """
    from android import activity as android_activity  # type: ignore[import-not-found]

    Intent = autoclass("android.content.Intent")
    String = autoclass("java.lang.String")  # noqa: N806 - Java class alias
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    android_activity_java = PythonActivity.mActivity
    if android_activity_java is None:
        raise RuntimeError("PythonActivity.mActivity is None; cannot open picker")

    already_delivered: list[bool] = [False]

    def _on_activity_result(request_code: int, result_code: int, intent_data: Any) -> None:
        if already_delivered[0]:
            return
        if request_code != _ANDROID_PICKER_REQUEST_CODE:
            return
        already_delivered[0] = True
        if result_code != -1:  # Activity.RESULT_OK == -1
            return
        if intent_data is None:
            return
        try:
            uri = intent_data.getData()
        except Exception as exc:
            print(f"[file_picker] getData failed: {exc}")
            return
        if uri is None:
            return
        try:
            cached_path = _copy_uri_to_cache(uri, android_activity_java)
        except Exception as exc:
            print(f"[file_picker] failed to import URI: {exc}")
            import traceback

            traceback.print_exc()
            return
        if cached_path is None:
            return
        Clock.schedule_once(lambda _dt: on_selected(cached_path), 0)

    android_activity.bind(on_activity_result=_on_activity_result)

    intent = Intent(Intent.ACTION_GET_CONTENT)
    intent.setType(String("image/*"))
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    android_activity_java.startActivityForResult(intent, _ANDROID_PICKER_REQUEST_CODE)


def _copy_uri_to_cache(uri: Any, android_activity_java: Any) -> Path | None:
    """Copy the bytes behind a ``content://`` URI into the app-private cache."""
    app = App.get_running_app()
    if app is None:
        return None
    cache_dir = Path(app.user_data_dir) / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    resolver = android_activity_java.getContentResolver()
    mime = (resolver.getType(uri) or "image/jpeg").lower()
    if "png" in mime:
        ext = ".png"
    elif "jpeg" in mime or "jpg" in mime:
        ext = ".jpg"
    else:
        ext = ".bin"
    dest = cache_dir / f"pick_{int(time.time() * 1000)}{ext}"

    istream = resolver.openInputStream(uri)
    total = 0
    buffer_size = 65536
    try:
        # A Python bytearray gets marshalled into a Java byte[] by pyjnius.
        java_buffer = bytearray(buffer_size)
        with dest.open("wb") as dst:
            while True:
                n = istream.read(java_buffer)
                if n < 0:
                    break
                if n == 0:
                    continue
                dst.write(bytes(java_buffer[:n]))
                total += n
                if total > _MAX_URI_COPY_BYTES:
                    dest.unlink(missing_ok=True)
                    raise OSError(
                        f"文件超过 {_MAX_URI_COPY_BYTES // (1024 * 1024)} MiB 上限"
                    )
    finally:
        istream.close()
    return dest


# ---------------------------------------------------------------------------
# PC / desktop: Kivy FileChooser
# ---------------------------------------------------------------------------


def _initial_directory() -> str:
    """Where the desktop file picker opens by default."""
    for candidate in (
        os.environ.get("REVERSIBLE_MOSAIC_PICKER_ROOT"),
        str(Path.home()),
    ):
        if candidate and os.path.isdir(candidate):
            return candidate
    return "."


def _open_kivy_filechooser(on_selected: SelectionCallback) -> Popup:
    """Show the modal FileChooser popup for non-Android platforms."""
    root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
    header = Label(
        text="选择一张 PNG 或 JPEG 图片",
        size_hint_y=None,
        height=dp(32),
    )
    chooser = FileChooserListView(
        path=_initial_directory(),
        filters=list(_SUPPORTED_FILTERS),
    )
    action_row = BoxLayout(
        orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8)
    )
    cancel_btn = Button(text="取消")
    confirm_btn = Button(text="使用此文件")
    action_row.add_widget(cancel_btn)
    action_row.add_widget(confirm_btn)
    root.add_widget(header)
    root.add_widget(chooser)
    root.add_widget(action_row)

    popup = Popup(
        title="选择图片",
        content=root,
        size_hint=(0.95, 0.95),
        auto_dismiss=False,
    )

    def _confirm(_button: Button) -> None:
        if not chooser.selection:
            header.text = "请先选中一个文件"
            return
        first = Path(chooser.selection[0])
        popup.dismiss()
        on_selected(first)

    def _cancel(_button: Button) -> None:
        popup.dismiss()

    confirm_btn.bind(on_release=_confirm)
    cancel_btn.bind(on_release=_cancel)

    popup.open()
    return popup
