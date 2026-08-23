"""Android-native gateway implementations.

Two gateways live here because they share the same platform boundary (PyJNIus,
Android SDK autoclasses) and load-time gate (:func:`is_available`). Splitting
them across files would double the JNI-helper surface and make the "Android
side of gateways" harder to eyeball.

Contents:

* :class:`AndroidOutputGateway` — writes finished PNGs into
  ``Pictures/ReversibleMosaic`` via MediaStore, opens them for viewing, and
  shares them via ``Intent.ACTION_SEND``. Uses ``IS_PENDING`` on API 29+ and
  falls back to insert-then-MediaScanner on API 26-28. On any write / verify
  failure the pending row is deleted so no half-file is ever visible
  (FR-SAVE-006). Cleans up its own orphan pending rows at app startup
  (FR-TASK-006 / §9.2 item 3).
* :class:`AndroidClipboardGateway` — copies a share code and tags the
  ``ClipDescription`` with ``EXTRA_IS_SENSITIVE`` on Android 13+ so the
  system's clipboard preview redacts the value (FR-ENC-007).

The desktop mirrors of these two live in :mod:`reversible_mosaic.android.desktop`.
Callers select the right implementation via :func:`is_available` — the app
constructs :class:`Android*Gateway` when it's True, otherwise the desktop stub.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Platform gate + shared JNI helpers
# ---------------------------------------------------------------------------

_RELATIVE_PATH = "Pictures/ReversibleMosaic"
_MIME_TYPE = "image/png"
_CLIP_LABEL = "reversible_mosaic_share_code"


def is_available() -> bool:
    """Return True if PyJNIus is importable (i.e. we are on Android)."""
    try:
        import jnius  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def _autoclass(name: str) -> Any:
    from jnius import autoclass

    return autoclass(name)


def _cast(target_class: str, value: Any) -> Any:
    """Force PyJNIus overload resolution to use a specific target class.

    PyJNIus can throw JavaMethodResolutionError on Java methods with many
    overloads (Intent.putExtra has ~24; ContentValues.put has ~10). Casting
    the argument to the exact declared parameter type pins the overload
    unambiguously.
    """
    from jnius import cast

    return cast(target_class, value)


def _python_activity() -> Any:
    activity = _autoclass("org.kivy.android.PythonActivity").mActivity
    if activity is None:
        raise AndroidMediaStoreError("PythonActivity.mActivity is None")
    return activity


def _api_level() -> int:
    return int(_autoclass("android.os.Build$VERSION").SDK_INT)


def _string_array(items: list[str]) -> Any:
    String = _autoclass("java.lang.String")
    return [String(v) for v in items]


# ---------------------------------------------------------------------------
# MediaStore output gateway
# ---------------------------------------------------------------------------


class AndroidMediaStoreError(RuntimeError):
    """Raised when MediaStore insertion, write, or verification fails."""


class AndroidOutputGateway:
    """Concrete :class:`OutputGateway` backed by Android's MediaStore.

    Instances are cheap; JNI classes are resolved lazily inside each method so
    PC-side tests can import this module without pulling in ``jnius``.
    """

    def __init__(self) -> None:
        if not is_available():
            raise RuntimeError("AndroidOutputGateway requires PyJNIus (Android only)")

    # -- publish -----------------------------------------------------------

    def publish_png(self, source: Path, display_name: str) -> str:
        """Insert ``source`` into MediaStore under ``Pictures/ReversibleMosaic``.

        Returns the ``content://media/external/images/media/<id>`` URI as a
        string. Raises :class:`AndroidMediaStoreError` on any failure and
        deletes the pending row so no half-file is left behind.
        """
        source_path = Path(source)
        if not source_path.is_file():
            raise AndroidMediaStoreError(f"源文件不存在: {source_path}")

        activity = _python_activity()
        resolver = activity.getContentResolver()
        api_level = _api_level()

        final_name = self._unique_display_name(resolver, display_name, api_level)
        values = _build_content_values(final_name, api_level)
        collection_uri = _images_external_uri(api_level)
        item_uri = resolver.insert(collection_uri, values)
        if item_uri is None:
            raise AndroidMediaStoreError("MediaStore.insert 返回 null")

        try:
            _copy_file_to_uri(resolver, source_path, item_uri)
            _verify_media_store_bytes(resolver, item_uri, source_path)
        except Exception as exc:
            _safe_delete(resolver, item_uri)
            raise AndroidMediaStoreError(f"MediaStore 写入失败: {exc}") from exc

        try:
            if api_level >= 29:
                _clear_pending(resolver, item_uri)
            else:
                _notify_media_scanner(activity, item_uri)
        except Exception as exc:
            _safe_delete(resolver, item_uri)
            raise AndroidMediaStoreError(f"MediaStore 提交失败: {exc}") from exc

        return str(item_uri.toString())

    # -- view / share ------------------------------------------------------

    def open_for_view(self, handle: str) -> None:
        _start_activity(handle, action="view")

    def share(self, handle: str, subject: str) -> None:
        """Backward-compatible alias for :meth:`share_original`."""
        self.share_original(handle, subject)

    def share_original(self, handle: str, subject: str) -> None:
        """Share the saved PNG itself through a temporary readable URI.

        The chooser receives the exact MediaStore URI rather than a bitmap or
        cache copy, so file-capable receivers can retain the PNG bytes and PNG
        metadata. A receiver can still independently transcode after accepting
        it; the UI tells the user to select its file/original-send option.
        """
        _start_activity(handle, action="share_original", subject=subject)

    # -- startup housekeeping ---------------------------------------------

    def cleanup_orphan_pending(self) -> int:
        """Delete this app's ``IS_PENDING=1`` rows left over from prior runs.

        Runs once at app startup (FR-TASK-006 / §9.2 item 3). Returns the
        number of rows deleted; all failures are swallowed so a busted cleanup
        never blocks app launch.
        """
        api_level = _api_level()
        if api_level < 29:
            return 0
        try:
            activity = _python_activity()
            resolver = activity.getContentResolver()
            collection_uri = _images_external_uri(api_level)
            selection = "is_pending=1 AND relative_path LIKE ?"
            args = [f"{_RELATIVE_PATH}%"]
            cursor = resolver.query(
                collection_uri,
                _string_array(["_id"]),
                selection,
                _string_array(args),
                None,
            )
            if cursor is None:
                return 0
            deleted = 0
            try:
                while cursor.moveToNext():
                    row_id = cursor.getLong(0)
                    row_uri = _content_uri_with_id(collection_uri, row_id)
                    try:
                        if resolver.delete(row_uri, None, None) > 0:
                            deleted += 1
                    except Exception:
                        continue
            finally:
                cursor.close()
            return deleted
        except Exception:
            return 0

    # -- helpers ----------------------------------------------------------

    def _unique_display_name(self, resolver: Any, requested: str, api_level: int) -> str:
        """Increment ``requested`` with ``_1/_2/...`` until MediaStore has no match.

        Only runs on API 29+ (RELATIVE_PATH-aware query). On older releases we
        pass the requested name straight through and rely on the file system to
        refuse duplicates via a fresh insert-fail-delete cycle.
        """
        if api_level < 29:
            return requested
        try:
            stem = Path(requested).stem
            ext = Path(requested).suffix or ".png"
            for attempt in range(0, 1000):
                candidate = requested if attempt == 0 else f"{stem}_{attempt}{ext}"
                if not _media_store_has_name(resolver, candidate, api_level):
                    return candidate
        except Exception:
            return requested
        return requested


def _images_external_uri(api_level: int) -> Any:
    MediaStoreImages = _autoclass("android.provider.MediaStore$Images$Media")
    if api_level >= 29:
        String = _autoclass("java.lang.String")
        return MediaStoreImages.getContentUri(String("external"))
    return MediaStoreImages.EXTERNAL_CONTENT_URI


def _build_content_values(display_name: str, api_level: int) -> Any:
    ContentValues = _autoclass("android.content.ContentValues")
    values = ContentValues()
    values.put("_display_name", display_name)
    values.put("mime_type", _MIME_TYPE)
    if api_level >= 29:
        values.put("relative_path", _RELATIVE_PATH)
        # ContentValues.put has ~10 overloads (put(String, Byte/Integer/Long/…));
        # a bare Python int makes PyJNIus throw a JavaMethodResolutionError
        # listing all candidates. Wrap in java.lang.Integer to pin the overload.
        Integer = _autoclass("java.lang.Integer")
        values.put("is_pending", Integer(1))
    return values


def _copy_file_to_uri(resolver: Any, source: Path, item_uri: Any) -> None:
    out_stream = resolver.openOutputStream(item_uri)
    if out_stream is None:
        raise AndroidMediaStoreError("openOutputStream 返回 null")
    try:
        with source.open("rb") as src:
            while True:
                chunk = src.read(65536)
                if not chunk:
                    break
                out_stream.write(chunk)
        out_stream.flush()
    finally:
        out_stream.close()


def _verify_media_store_bytes(resolver: Any, item_uri: Any, source: Path) -> None:
    """Re-read the freshly written MediaStore file and hash-compare it.

    Uses SHA-256 stream digests to keep memory bounded (mirrors
    ``normalize.write_png``'s post-write ``np.array_equal`` check but works
    over the platform stream).
    """
    import hashlib

    expected = hashlib.sha256()
    with source.open("rb") as src:
        for chunk in iter(lambda: src.read(65536), b""):
            expected.update(chunk)

    actual = hashlib.sha256()
    in_stream = resolver.openInputStream(item_uri)
    if in_stream is None:
        raise AndroidMediaStoreError("openInputStream 返回 null")
    try:
        java_buffer = bytearray(65536)
        while True:
            n = in_stream.read(java_buffer)
            if n < 0:
                break
            if n == 0:
                continue
            actual.update(bytes(java_buffer[:n]))
    finally:
        in_stream.close()

    if expected.digest() != actual.digest():
        raise AndroidMediaStoreError("MediaStore 复读校验失败: SHA-256 不一致")


def _clear_pending(resolver: Any, item_uri: Any) -> None:
    ContentValues = _autoclass("android.content.ContentValues")
    Integer = _autoclass("java.lang.Integer")
    values = ContentValues()
    # Same PyJNIus overload-ambiguity workaround as _build_content_values.
    values.put("is_pending", Integer(0))
    resolver.update(item_uri, values, None, None)


def _notify_media_scanner(activity: Any, item_uri: Any) -> None:
    Intent = _autoclass("android.content.Intent")
    intent = Intent(Intent.ACTION_MEDIA_SCANNER_SCAN_FILE)
    intent.setData(item_uri)
    activity.sendBroadcast(intent)


def _safe_delete(resolver: Any, item_uri: Any) -> None:
    try:
        resolver.delete(item_uri, None, None)
    except Exception:
        return


def _content_uri_with_id(collection_uri: Any, row_id: int) -> Any:
    ContentUris = _autoclass("android.content.ContentUris")
    return ContentUris.withAppendedId(collection_uri, row_id)


def _media_store_has_name(resolver: Any, display_name: str, api_level: int) -> bool:
    """Query MediaStore for an existing row with this display_name + our path."""
    try:
        collection_uri = _images_external_uri(api_level)
        selection = "_display_name=? AND relative_path=?"
        args = _string_array([display_name, f"{_RELATIVE_PATH}/"])
        cursor = resolver.query(
            collection_uri, _string_array(["_id"]), selection, args, None
        )
        if cursor is None:
            return False
        try:
            return bool(int(cursor.getCount()) > 0)
        finally:
            cursor.close()
    except Exception:
        return False


def _start_activity(handle: str, *, action: str, subject: str | None = None) -> None:
    Intent = _autoclass("android.content.Intent")
    Uri = _autoclass("android.net.Uri")
    String = _autoclass("java.lang.String")
    activity = _python_activity()

    uri = Uri.parse(String(handle))
    if action == "view":
        intent = Intent(Intent.ACTION_VIEW)
        # Wildcard MIME so viewers that only register for image/* (not the
        # exact image/png) still pick this up.
        intent.setDataAndType(uri, String("image/*"))
    elif action in {"share", "share_original"}:
        intent = Intent(Intent.ACTION_SEND)
        intent.setType(String(_MIME_TYPE))
        # PyJNIus overload disambiguation — Intent.putExtra has ~24 overloads
        # (Parcelable / Parcelable[] / Serializable / CharSequence / String
        # / boolean[] / …). Uri implements Parcelable AND Serializable, so
        # PyJNIus can't decide without an explicit cast. Same class of bug
        # as ContentValues.put(String, Integer). Cast pins the target
        # signature to `putExtra(String, Parcelable)`.
        intent.putExtra(Intent.EXTRA_STREAM, _cast("android.os.Parcelable", uri))
        if subject:
            intent.putExtra(
                Intent.EXTRA_SUBJECT,
                _cast("java.lang.CharSequence", String(subject)),
            )
    else:
        raise ValueError(f"未知 action: {action}")

    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    if action in {"share", "share_original"}:
        chooser_title_text = (
            "原图/文件分享" if action == "share_original" else "分享打码结果"
        )
        chooser_title = _cast(
            "java.lang.CharSequence", String(chooser_title_text)
        )
        chooser = Intent.createChooser(intent, chooser_title)
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        activity.startActivity(chooser)
    else:
        activity.startActivity(intent)


# ---------------------------------------------------------------------------
# Clipboard gateway
# ---------------------------------------------------------------------------


class AndroidClipboardGateway:
    """Concrete :class:`ClipboardGateway` backed by ``ClipboardManager``.

    On Android 13+ (API 33) tags the clip's ``ClipDescription`` with
    ``EXTRA_IS_SENSITIVE`` so the system UI redacts the value in the copy-
    preview toast (FR-ENC-007). Older releases silently ignore the extra.
    """

    def __init__(self) -> None:
        if not is_available():
            raise RuntimeError("AndroidClipboardGateway requires PyJNIus (Android only)")

    def copy_sensitive(self, text: str) -> bool:
        """Copy ``text`` and mark it sensitive if the OS supports it.

        Returns whether the primary clipboard was actually updated. Failures
        remain non-fatal, but callers can now avoid claiming a failed copy
        succeeded.
        """
        try:
            Context = _autoclass("android.content.Context")
            PythonActivity = _autoclass("org.kivy.android.PythonActivity")
            ClipData = _autoclass("android.content.ClipData")
            String = _autoclass("java.lang.String")

            activity = PythonActivity.mActivity
            if activity is None:
                return False
            manager = activity.getSystemService(Context.CLIPBOARD_SERVICE)
            if manager is None:
                return False
            clip = ClipData.newPlainText(String(_CLIP_LABEL), String(text))

            if _api_level() >= 33:
                try:
                    PersistableBundle = _autoclass("android.os.PersistableBundle")
                    ClipDescription = _autoclass("android.content.ClipDescription")
                    extras = PersistableBundle()
                    extras.putBoolean(
                        String(ClipDescription.EXTRA_IS_SENSITIVE), True
                    )
                    clip.getDescription().setExtras(extras)
                except Exception:
                    # Extra fields are decorative; don't fail the copy.
                    pass

            manager.setPrimaryClip(clip)
            return True
        except Exception:
            return False


__all__ = [
    "AndroidClipboardGateway",
    "AndroidMediaStoreError",
    "AndroidOutputGateway",
    "is_available",
]
