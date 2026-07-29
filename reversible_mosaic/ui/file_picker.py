"""Modal file picker for encode/decode screens.

The MVP uses Kivy's built-in ``FileChooserListView`` inside a ``Popup``. This
gives a portable path picker on PC that also runs (though not ideally) on
Android. Stage 2 later swaps this for the Android Photo Picker via pyjnius —
the interface below stays the same so the screens don't have to change.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

try:
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.filechooser import FileChooserListView
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("请安装 app 依赖后启动界面: pip install -e '.[app]'") from exc


SelectionCallback = Callable[[Path], None]

_SUPPORTED_FILTERS = ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG")


def _initial_directory() -> str:
    """Where the file picker opens by default.

    PC: the user's home. Android: `/sdcard/Pictures` when it exists, else the
    external storage root. `FileChooser` cannot browse into ``content://`` URIs,
    so on Android this is a best-effort until the Photo Picker gateway lands.
    """
    for candidate in (
        os.environ.get("REVERSIBLE_MOSAIC_PICKER_ROOT"),
        "/sdcard/Pictures",
        "/sdcard",
        str(Path.home()),
    ):
        if candidate and os.path.isdir(candidate):
            return candidate
    return "."


def open_file_picker(on_selected: SelectionCallback) -> Popup:
    """Show the modal picker and invoke ``on_selected`` when the user confirms."""
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
    action_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
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
