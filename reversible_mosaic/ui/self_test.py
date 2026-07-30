"""Stage-0 diagnostic screen.

Verifies that each newly-added arm64 native dependency (pyjnius / numpy /
pillow / cython v1) actually loads and works on-device. Also runs a
performance scan and persists results into the app's private data dir.

This screen is temporary. Once Stage 0 exits, the entry button in
:mod:`reversible_mosaic.app` is removed but this module stays for regression.
"""

from __future__ import annotations

import io
import json
import platform
import sys
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.screenmanager import Screen
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.textinput import TextInput
except ImportError as exc:  # pragma: no cover - matches app.py's boundary
    raise RuntimeError("请安装 app 依赖后启动界面: pip install -e '.[app]'") from exc


def _peak_rss_bytes() -> int | None:
    try:
        import resource
    except ImportError:
        resource = None  # type: ignore[assignment]
    if resource is not None:
        try:
            getrusage = getattr(resource, "getrusage", None)
            rusage_self = getattr(resource, "RUSAGE_SELF", None)
            if getrusage is not None and rusage_self is not None:
                max_rss = int(getrusage(rusage_self).ru_maxrss)
                if sys.platform == "darwin":
                    return max_rss
                return max_rss * 1024
        except Exception:
            pass
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmPeak:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        return None
    return None


def _fmt_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"


def _probe_pyjnius() -> str:
    from jnius import autoclass  # type: ignore[import-not-found]

    activity_cls = autoclass("org.kivy.android.PythonActivity")
    activity = getattr(activity_cls, "mActivity", None)
    package_name = "<no context>"
    if activity is not None:
        try:
            context = activity.getApplicationContext()
            package_name = context.getPackageName()
        except Exception as exc:  # pragma: no cover - runtime-only
            package_name = f"<context error: {exc!r}>"
    return f"autoclass OK; package={package_name}"


def _probe_numpy() -> str:
    import numpy as np

    arr = np.arange(64, dtype=np.uint8).reshape((4, 4, 4))
    doubled = (arr.astype(np.uint16) * 2 % 256).astype(np.uint8)
    if doubled.shape != arr.shape or doubled.dtype != np.uint8:
        raise AssertionError(f"numpy 运算结果异常: shape={doubled.shape} dtype={doubled.dtype}")
    if int(doubled[0, 0, 0]) != 0 or int(doubled[3, 3, 3]) != (63 * 2) % 256:
        raise AssertionError("numpy 逐元素运算值不正确")
    return f"numpy={np.__version__}, arr.shape={doubled.shape}, dtype={doubled.dtype}"


def _probe_pillow() -> str:
    import numpy as np
    import PIL
    from PIL import Image

    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    arr[:, :, 0] = 200
    arr[:, :, 1] = 100
    arr[:, :, 2] = 50
    arr[:, :, 3] = np.array([[0, 128, 255, 0]] * 4, dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    payload_len = len(buf.getvalue())
    buf.seek(0)
    decoded = np.array(Image.open(buf).convert("RGBA"))
    if not np.array_equal(arr, decoded):
        raise AssertionError("PNG round-trip lost pixels")
    return f"PIL={PIL.__version__}, 4x4 RGBA PNG={payload_len}B round-trip OK"


def _probe_reference_v1() -> str:
    import numpy as np

    from reversible_mosaic.core.algorithm.reference_v1 import decrypt, encrypt

    original = np.zeros((4, 4, 4), dtype=np.uint8)
    original[:, :, 0] = 200
    original[:, :, 1] = 100
    original[:, :, 2] = 50
    # alpha stays 0 for every pixel — this is the transparent-RGB preservation case.

    lines: list[str] = []
    for rounds in (2, 5, 30):
        encrypted = encrypt(original, seed=500000, rounds=rounds)
        restored = decrypt(encrypted, seed=500000, rounds=rounds)
        if not np.array_equal(original, restored):
            max_diff = int(np.abs(original.astype(int) - restored.astype(int)).max())
            raise AssertionError(f"rounds={rounds}: RGBA矩阵未复原 (max_diff={max_diff})")
        if not np.array_equal(original[:, :, :3], restored[:, :, :3]):
            raise AssertionError(f"rounds={rounds}: 透明像素的 RGB 通道被改动")
        lines.append(f"rounds={rounds}: 逐字节相等")
    return "参考实现在 4x4 全透明 RGBA 上零差异; " + " / ".join(lines)


def _probe_v1_cython() -> str:
    try:
        import reversible_mosaic.core.algorithm.v1 as v1_cython  # type: ignore[import-not-found]
    except ImportError as exc:
        return f"NOT_BUILT: {exc}"

    import numpy as np

    # 4x4 RGBA test pattern (H x W x C = 4 x 4 x 4 uint8, C-contiguous)
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    pixels[..., 0] = np.arange(16, dtype=np.uint8).reshape(4, 4) * 15
    pixels[..., 1] = 100
    pixels[..., 2] = 50
    pixels[..., 3] = 255
    backup = pixels.copy()

    # V1 定稿: neighborhood_swap_forward/inverse (radius = min(4,4)//32 = 0
    # would be floored to 8 by domain layer, but Cython takes radius directly;
    # use 2 here so we get actual swaps on a 4x4 image).
    key = 0xDEADBEEFCAFEBABE
    v1_cython.neighborhood_swap_forward(pixels, key, 2)
    v1_cython.neighborhood_swap_inverse(pixels, key, 2)
    if not np.array_equal(pixels, backup):
        raise AssertionError("neighborhood_swap forward+inverse 未复原")
    return "Cython 模块加载 OK; neighborhood_swap forward/inverse 复原一致"


SYNC_PROBES: list[tuple[str, Callable[[], str]]] = [
    ("pyjnius", _probe_pyjnius),
    ("numpy", _probe_numpy),
    ("pillow", _probe_pillow),
    ("V1 参考实现 (4x4 RGBA alpha=0)", _probe_reference_v1),
    ("V1 Cython 优化", _probe_v1_cython),
]


class SelfTestScreen(Screen):  # type: ignore[misc]
    """Screen with buttons for each Stage-0 probe."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._perf_thread: threading.Thread | None = None
        self._perf_cancel = threading.Event()
        self._results_log = TextInput(
            readonly=True,
            font_size=dp(12),
            size_hint_y=None,
            text=self._banner_text(),
        )
        self._results_log.bind(minimum_height=self._results_log.setter("height"))
        self._build_widget_tree()

    def _banner_text(self) -> str:
        return (
            "阶段 0 自检面板\n"
            f"Python {sys.version.split()[0]}  平台 {platform.machine()} {platform.system()}\n"
            "按下按钮开始探针; 每项独立运行, 未打包依赖显示 NOT_BUILT。\n"
            "----------------------------------\n"
        )

    def _build_widget_tree(self) -> None:
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(8))

        title = Label(
            text="阶段 0 自检",
            font_size=dp(22),
            size_hint_y=None,
            height=dp(40),
        )
        root.add_widget(title)

        for label, callback in SYNC_PROBES:
            btn = Button(text=label, size_hint_y=None, height=dp(44))
            btn.bind(on_release=lambda _b, cb=callback, lbl=label: self._run_sync_probe(lbl, cb))
            root.add_widget(btn)

        perf_btn = Button(
            text="性能扫描 (1920x1080 RGB, 2/5/15/30 轮, 5 次中位数)",
            size_hint_y=None,
            height=dp(52),
        )
        perf_btn.bind(on_release=lambda _b: self._start_perf_scan())
        root.add_widget(perf_btn)

        cancel_btn = Button(
            text="取消性能扫描",
            size_hint_y=None,
            height=dp(40),
        )
        cancel_btn.bind(on_release=lambda _b: self._cancel_perf_scan())
        root.add_widget(cancel_btn)

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self._results_log)
        root.add_widget(scroll)

        clear_btn = Button(
            text="清空结果",
            size_hint_y=None,
            height=dp(36),
        )
        clear_btn.bind(on_release=lambda _b: self._clear_results())
        root.add_widget(clear_btn)

        back_btn = Button(
            text="返回首页",
            size_hint_y=None,
            height=dp(44),
        )
        back_btn.bind(on_release=lambda _b: self._go_home())
        root.add_widget(back_btn)

        self.add_widget(root)

    def _go_home(self) -> None:
        if self.manager is not None:
            self.manager.current = "home"

    def _clear_results(self) -> None:
        self._results_log.text = self._banner_text()

    def _append_line(self, line: str) -> None:
        self._results_log.text = self._results_log.text + line + "\n"

    def _run_sync_probe(self, label: str, callback: Callable[[], str]) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._append_line(f"[{stamp}] {label}: 运行中...")
        try:
            result = callback()
            self._append_line(f"[{stamp}] {label}: PASS  {result}")
        except Exception as exc:
            tb = traceback.format_exception_only(type(exc), exc)[0].strip()
            self._append_line(f"[{stamp}] {label}: FAIL  {tb}")

    def _start_perf_scan(self) -> None:
        if self._perf_thread is not None and self._perf_thread.is_alive():
            self._append_line("性能扫描已在运行; 请先取消。")
            return
        self._perf_cancel.clear()
        stamp = time.strftime("%H:%M:%S")
        self._append_line(f"[{stamp}] 性能扫描: 启动 (worker thread)")
        self._perf_thread = threading.Thread(
            target=self._perf_scan_worker, name="stage0-perf-scan", daemon=True
        )
        self._perf_thread.start()

    def _cancel_perf_scan(self) -> None:
        if self._perf_thread is None or not self._perf_thread.is_alive():
            self._append_line("性能扫描未运行。")
            return
        self._perf_cancel.set()
        self._append_line("已发送取消信号; 等待 worker 在下一个 checkpoint 结束。")

    def _perf_scan_worker(self) -> None:
        started = time.time()
        try:
            summary = self._run_perf_scan()
        except Exception as exc:
            tb = "\n".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            Clock.schedule_once(
                lambda _dt, tb=tb: self._append_line(f"性能扫描: FAIL\n{tb}"), 0
            )
            return
        elapsed = time.time() - started

        def _finish(
            _dt: float,
            summary: dict[str, Any] = summary,
            elapsed: float = elapsed,
        ) -> None:
            self._append_line("性能扫描: 完成")
            self._append_line(f"  总耗时 {elapsed:.1f}s, 实现={summary['implementation']}")
            for row in summary["rows"]:
                self._append_line(
                    f"  rounds={row['rounds']:>2}: "
                    f"median={row['median_s']:.3f}s "
                    f"p95={row['p95_s']:.3f}s "
                    f"peak_rss={_fmt_bytes(row['peak_rss_bytes'])}"
                )
            self._append_line(f"  已写入 {summary['saved_to']}")

        Clock.schedule_once(_finish, 0)

    def _run_perf_scan(self) -> dict[str, Any]:
        import numpy as np

        from reversible_mosaic.core.algorithm.registry import get, v1_implementation

        backend = v1_implementation()
        descriptor = get(1)
        # AC-PERF target: 1920x1080 8-bit RGB, 1 round <= 3s, 10 rounds <= 18s,
        # 20 rounds <= 35s. With Cython v1 wired into the pipeline we exercise
        # the exact path the encode/decode screens will use.
        implementation = f"registry V1 backend = {backend}"
        width, height = 1920, 1080

        rng = np.random.default_rng(seed=12345)
        original = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)

        rows: list[dict[str, Any]] = []
        for rounds in (2, 5, 15, 30):
            if self._perf_cancel.is_set():
                break
            durations: list[float] = []
            peak_rss_before = _peak_rss_bytes()
            for iteration in range(5):
                if self._perf_cancel.is_set():
                    break
                Clock.schedule_once(
                    lambda _dt, r=rounds, i=iteration: self._append_line(
                        f"  ...rounds={r} iter {i + 1}/5"
                    ),
                    0,
                )
                t0 = time.perf_counter()
                encrypted = descriptor.encrypt(original, 500000, rounds, None)
                _ = descriptor.decrypt(encrypted, 500000, rounds, None)
                elapsed = time.perf_counter() - t0
                durations.append(elapsed)
            if not durations:
                continue
            durations_sorted = sorted(durations)
            median = durations_sorted[len(durations_sorted) // 2]
            p95 = durations_sorted[-1]
            peak_rss_after = _peak_rss_bytes()
            rows.append(
                {
                    "rounds": rounds,
                    "iterations": durations,
                    "median_s": median,
                    "p95_s": p95,
                    "peak_rss_bytes": peak_rss_after or peak_rss_before,
                }
            )

        summary: dict[str, Any] = {
            "implementation": implementation,
            "backend": backend,
            "resolution": f"{width}x{height}",
            "rows": rows,
            "cancelled": self._perf_cancel.is_set(),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "python": sys.version.split()[0],
            "machine": platform.machine(),
        }
        summary["saved_to"] = str(self._save_summary(summary))
        return summary

    def _save_summary(self, summary: dict[str, Any]) -> Path:
        app = App.get_running_app()
        base = Path(app.user_data_dir) if app is not None else Path.cwd()
        base.mkdir(parents=True, exist_ok=True)
        target = base / "stage0_perf.json"
        target.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return target
