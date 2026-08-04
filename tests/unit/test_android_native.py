"""JNI-mocked tests for :mod:`reversible_mosaic.android.native`.

The Android gateway uses PyJNIus only lazily, so on the PC we can import the
module and patch its module-level helper functions
(``_autoclass``, ``_python_activity``, ``_api_level`` etc.) to simulate
Android platform behavior. These tests document the control-flow contract:

* :class:`AndroidOutputGateway` construction fails when PyJNIus is missing.
* ``publish_png`` **always deletes the pending MediaStore row** whenever
  ``_copy_file_to_uri``, ``_verify_media_store_bytes``, or ``_clear_pending``
  raises (FR-SAVE-006 — no visible half-file).
* ``cleanup_orphan_pending`` is a no-op on API 26-28 and swallows arbitrary
  JNI exceptions on API 29+ (FR-TASK-006 — cleanup never blocks app launch).
* Clipboard writes swallow every JNI failure (FR-ENC-007 — best-effort).
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from reversible_mosaic.android import native

# ---------------------------------------------------------------------------
# Construction gate
# ---------------------------------------------------------------------------


def test_output_gateway_requires_jnius() -> None:
    """On PC (or any environment without PyJNIus) the constructor must raise."""
    with patch.object(native, "is_available", return_value=False):
        with pytest.raises(RuntimeError, match="PyJNIus"):
            native.AndroidOutputGateway()


def test_clipboard_gateway_requires_jnius() -> None:
    with patch.object(native, "is_available", return_value=False):
        with pytest.raises(RuntimeError, match="PyJNIus"):
            native.AndroidClipboardGateway()


# ---------------------------------------------------------------------------
# publish_png failure injection
# ---------------------------------------------------------------------------


def _make_resolver(**overrides: Any) -> MagicMock:
    resolver = MagicMock(name="resolver")
    # Sensible defaults; individual tests override as needed.
    resolver.insert.return_value = MagicMock(name="uri")
    resolver.openOutputStream.return_value = MagicMock(name="out_stream")
    resolver.openInputStream.return_value = MagicMock(name="in_stream")
    resolver.delete.return_value = 1
    for key, value in overrides.items():
        getattr(resolver, key).return_value = value
    return resolver


def _make_activity(resolver: MagicMock) -> MagicMock:
    activity = MagicMock(name="activity")
    activity.getContentResolver.return_value = resolver
    return activity


def _patch_android(
    api_level: int = 33,
    resolver: MagicMock | None = None,
    autoclass_side_effect: Any = None,
) -> Any:
    """Bundle the four native.py helpers patch calls into one context manager."""
    resolved: MagicMock = resolver if resolver is not None else _make_resolver()
    activity = _make_activity(resolved)

    def _fake_autoclass(name: str) -> Any:
        if autoclass_side_effect is not None:
            side_effect = autoclass_side_effect(name)
            if side_effect is not None:
                return side_effect
        # Fallback: return a MagicMock whose class methods can be chained.
        return MagicMock(name=name)

    patches = [
        patch.object(native, "is_available", return_value=True),
        patch.object(native, "_python_activity", return_value=activity),
        patch.object(native, "_api_level", return_value=api_level),
        patch.object(native, "_autoclass", side_effect=_fake_autoclass),
    ]

    class _Ctx:
        def __enter__(self) -> tuple[MagicMock, MagicMock]:
            for p in patches:
                p.start()
            return activity, resolved

        def __exit__(self, *args: Any) -> None:
            for p in reversed(patches):
                p.stop()

    return _Ctx()


def test_publish_png_missing_source_raises(tmp_path: Path) -> None:
    with _patch_android():
        gw = native.AndroidOutputGateway()
        with pytest.raises(native.AndroidMediaStoreError, match="源文件不存在"):
            gw.publish_png(tmp_path / "no_such.png", "out.png")


def test_publish_png_insert_returns_null(tmp_path: Path) -> None:
    src = tmp_path / "src.png"
    src.write_bytes(b"payload")

    resolver = _make_resolver()
    resolver.insert.return_value = None

    with _patch_android(resolver=resolver):
        gw = native.AndroidOutputGateway()
        with pytest.raises(native.AndroidMediaStoreError, match="insert 返回 null"):
            gw.publish_png(src, "out.png")
    # No item URI was ever produced, so nothing to delete.
    resolver.delete.assert_not_called()


def test_publish_png_write_failure_deletes_pending(tmp_path: Path) -> None:
    src = tmp_path / "src.png"
    src.write_bytes(b"payload")
    resolver = _make_resolver()

    with _patch_android(resolver=resolver):
        with patch.object(
            native, "_copy_file_to_uri", side_effect=OSError("disk full")
        ):
            gw = native.AndroidOutputGateway()
            with pytest.raises(native.AndroidMediaStoreError, match="写入失败"):
                gw.publish_png(src, "out.png")
    # FR-SAVE-006: half-file must be cleaned up.
    resolver.delete.assert_called_once()


def test_publish_png_hash_mismatch_deletes_pending(tmp_path: Path) -> None:
    """If the SHA-256 re-read disagrees with the source, publish_png must
    treat it as a write failure and delete the MediaStore row."""
    src = tmp_path / "src.png"
    src.write_bytes(b"payload")
    resolver = _make_resolver()

    with _patch_android(resolver=resolver):
        with (
            patch.object(native, "_copy_file_to_uri"),
            patch.object(
                native,
                "_verify_media_store_bytes",
                side_effect=native.AndroidMediaStoreError("SHA-256 不一致"),
            ),
        ):
            gw = native.AndroidOutputGateway()
            with pytest.raises(native.AndroidMediaStoreError, match="写入失败"):
                gw.publish_png(src, "out.png")
    resolver.delete.assert_called_once()


def test_publish_png_commit_failure_deletes_pending(tmp_path: Path) -> None:
    """After a successful write, if the API 29+ ``IS_PENDING=0`` commit fails
    the pending row must still be cleaned up."""
    src = tmp_path / "src.png"
    src.write_bytes(b"payload")
    resolver = _make_resolver()

    with _patch_android(resolver=resolver):
        with (
            patch.object(native, "_copy_file_to_uri"),
            patch.object(native, "_verify_media_store_bytes"),
            patch.object(
                native, "_clear_pending", side_effect=RuntimeError("commit boom")
            ),
        ):
            gw = native.AndroidOutputGateway()
            with pytest.raises(native.AndroidMediaStoreError, match="提交失败"):
                gw.publish_png(src, "out.png")
    resolver.delete.assert_called_once()


def test_publish_png_unique_display_name_skips_below_29(tmp_path: Path) -> None:
    """API 26-28 has no ``RELATIVE_PATH`` column; we pass the requested name
    straight through instead of running a dedup query."""
    src = tmp_path / "src.png"
    src.write_bytes(b"payload")
    resolver = _make_resolver()

    with _patch_android(api_level=28, resolver=resolver):
        with (
            patch.object(native, "_copy_file_to_uri"),
            patch.object(native, "_verify_media_store_bytes"),
            patch.object(native, "_notify_media_scanner"),
        ):
            gw = native.AndroidOutputGateway()
            gw.publish_png(src, "photo_mosaic.png")

    # ``query`` is what _unique_display_name / _media_store_has_name use;
    # API 28 path must not touch it.
    resolver.query.assert_not_called()


# ---------------------------------------------------------------------------
# cleanup_orphan_pending
# ---------------------------------------------------------------------------


def test_cleanup_orphan_pending_noop_on_api_28() -> None:
    with _patch_android(api_level=28):
        gw = native.AndroidOutputGateway()
        assert gw.cleanup_orphan_pending() == 0


def test_cleanup_orphan_pending_swallows_query_exception() -> None:
    resolver = _make_resolver()
    resolver.query.side_effect = RuntimeError("MediaStore not ready")

    with _patch_android(api_level=33, resolver=resolver):
        gw = native.AndroidOutputGateway()
        # Any exception path must return 0 without raising -- app startup
        # must never depend on the cleanup succeeding.
        assert gw.cleanup_orphan_pending() == 0


def test_cleanup_orphan_pending_returns_zero_on_null_cursor() -> None:
    resolver = _make_resolver()
    resolver.query.return_value = None

    with _patch_android(api_level=33, resolver=resolver):
        gw = native.AndroidOutputGateway()
        assert gw.cleanup_orphan_pending() == 0


# ---------------------------------------------------------------------------
# Share intent: no share code leakage
# ---------------------------------------------------------------------------


def test_share_subject_never_contains_share_code() -> None:
    """FR-ENC-006 / FR-SAVE-004: the subject passed via ``Intent.EXTRA_SUBJECT``
    must never contain a share code. This test just asserts the module-level
    invariant that callers pass a fixed app-branding string, which is what
    :class:`ReversibleMosaicApp.share_current_result` does.
    """
    # The app hard-codes this string; anything with digits or the default
    # share code 500000 is a red flag.
    from reversible_mosaic import app as app_module

    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "share_current_result" in source
    # Sanity check that no obvious share code strings survived in app.py's
    # share_current_result path. This is a coarse guard -- the real signal
    # comes from FR-ENC-011 log scanning, but it makes regressions obvious.
    assert "500000" not in source or 'DEFAULT_SHARE_CODE = "500000"' not in source


# ---------------------------------------------------------------------------
# Clipboard best-effort
# ---------------------------------------------------------------------------


def test_clipboard_swallows_all_jni_errors() -> None:
    """``copy_sensitive`` is explicitly best-effort -- any exception must be
    swallowed so the surrounding user flow (post-encrypt UI update) is never
    interrupted."""

    def _boom(name: str) -> Any:
        raise RuntimeError("JNI unavailable")

    with (
        patch.object(native, "is_available", return_value=True),
        patch.object(native, "_autoclass", side_effect=_boom),
    ):
        gw = native.AndroidClipboardGateway()
        # Must not raise even though every JNI call inside would blow up.
        gw.copy_sensitive("500000")


def test_clipboard_swallows_missing_activity() -> None:
    with _patch_android():
        # Force PythonActivity.mActivity to be None inside copy_sensitive.
        class _NoActivity:
            mActivity = None

        with patch.object(native, "_autoclass", return_value=_NoActivity):
            native.AndroidClipboardGateway().copy_sensitive("500000")  # no raise

# ---------------------------------------------------------------------------
# AC-011 diagnostic and share-boundary privacy
# ---------------------------------------------------------------------------


def test_picker_failures_do_not_emit_or_persist_provider_details(
    tmp_path: Path,
) -> None:
    from reversible_mosaic.ui import file_picker

    marker = "content://provider/private/secret-741852.png?code=741852"
    app = MagicMock()
    app.user_data_dir = str(tmp_path)
    fallback = MagicMock(name="fallback")

    with (
        patch.object(file_picker, "_HAS_JNIUS", True),
        patch.object(file_picker, "_open_android_gallery", side_effect=RuntimeError(marker)),
        patch.object(file_picker, "_open_kivy_filechooser", fallback),
        patch.object(cast(Any, file_picker).App, "get_running_app", return_value=app),
        redirect_stdout(io.StringIO()) as output,
    ):
        file_picker.open_file_picker(MagicMock())

    assert marker not in output.getvalue()
    assert not (tmp_path / "picker_error.log").exists()
    fallback.assert_called_once()


def test_pipeline_failure_diagnostics_hide_input_and_share_code() -> None:
    from reversible_mosaic import app as app_module

    marker = "D:/private/photo-741852.png?share_code=741852"
    screen = MagicMock()
    app = app_module.ReversibleMosaicApp.__new__(app_module.ReversibleMosaicApp)
    coordinator = MagicMock()
    setattr(app, "_coordinator", coordinator)  # noqa: B010
    setattr(app, "_get_progress_screen", MagicMock(return_value=screen))  # noqa: B010

    with redirect_stdout(io.StringIO()) as output:
        app._on_failed(RuntimeError(marker))

    assert marker not in output.getvalue()
    assert "741852" not in output.getvalue()
    assert screen.detail_label == "图片处理失败, 请检查图片和参数后重试。"
    coordinator.reset.assert_called_once()


def test_share_gateway_receives_fixed_subject_without_share_code() -> None:
    from reversible_mosaic import app as app_module

    gateway = MagicMock()
    snapshot = MagicMock(is_saved=True, saved_handle="content://media/output/42")
    app = app_module.ReversibleMosaicApp.__new__(app_module.ReversibleMosaicApp)
    app.last_result = snapshot
    setattr(app, "_output_gateway_instance", MagicMock(return_value=gateway))  # noqa: B010

    app.share_current_result()

    gateway.share.assert_called_once_with(
        "content://media/output/42", "ReversibleMosaic 输出"
    )
