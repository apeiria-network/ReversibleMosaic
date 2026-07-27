from __future__ import annotations

import pytest

from reversible_mosaic.domain.share_code import (
    DEFAULT_SHARE_CODE,
    ShareCodeError,
    generate_share_code,
    parse_share_code,
)


@pytest.mark.parametrize(
    ("raw", "normalized", "seed", "used_default"),
    [
        (None, DEFAULT_SHARE_CODE, 500000, True),
        ("", DEFAULT_SHARE_CODE, 500000, True),
        ("000123", "123", 123, False),
        ("000000", "0", 0, False),
        ("9999999999", "9999999999", 9_999_999_999, False),
    ],
)
def test_parse_share_code(
    raw: str | None, normalized: str, seed: int, used_default: bool
) -> None:
    parsed = parse_share_code(raw)
    assert parsed.normalized == normalized
    assert parsed.seed == seed
    assert parsed.used_default is used_default


@pytest.mark.parametrize(
    "raw", [" ", "-1", "+1", "1.0", "１２３", "12345678901"]  # noqa: RUF001
)
def test_reject_invalid_share_code(raw: str) -> None:
    with pytest.raises(ShareCodeError):
        parse_share_code(raw)


def test_generated_code_obeys_protocol() -> None:
    for _ in range(100):
        generated = generate_share_code()
        assert len(generated.normalized) == 6
        assert 100000 <= generated.seed <= 999999
        assert generated.seed != 500000
