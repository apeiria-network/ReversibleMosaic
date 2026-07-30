"""Verify the Stage-0 diagnostic probes run on PC before shipping to arm64.

The screen itself lives in :mod:`reversible_mosaic.ui.self_test` and is
skipped if Kivy is not installed (dev env has it via ``.[app]``). We only
exercise the PC-runnable probes; the pyjnius probe intentionally fails on
PC and is validated on-device.
"""

from __future__ import annotations

import pytest

pytest.importorskip("kivy", reason="self_test screen requires kivy from .[app]")

from reversible_mosaic.ui import self_test


def test_numpy_probe_returns_summary() -> None:
    result = self_test._probe_numpy()
    assert "numpy=" in result
    assert "dtype=uint8" in result


def test_pillow_probe_round_trips_rgba() -> None:
    result = self_test._probe_pillow()
    assert "round-trip OK" in result
    assert "PIL=" in result


def test_reference_v1_probe_covers_transparent_rgba() -> None:
    result = self_test._probe_reference_v1()
    assert "零差异" in result
    for rounds in (2, 5, 30):
        assert f"rounds={rounds}" in result


def test_pyjnius_probe_fails_off_device() -> None:
    with pytest.raises(ImportError):
        self_test._probe_pyjnius()


def test_v1_cython_probe_reports_status() -> None:
    result = self_test._probe_v1_cython()
    assert result.startswith("NOT_BUILT") or "Cython 模块加载 OK" in result
