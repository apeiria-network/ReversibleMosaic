"""Sharing-code validation and normalization."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

DEFAULT_SHARE_CODE = "500000"
MIN_RANDOM_CODE = 100000
MAX_RANDOM_CODE = 999999
MAX_SEED = 9_999_999_999


class ShareCodeError(ValueError):
    """Raised when a sharing code does not match the public protocol."""


@dataclass(frozen=True, slots=True)
class ShareCode:
    """A normalized sharing code and its numeric seed."""

    normalized: str
    seed: int
    used_default: bool


def parse_share_code(value: str | None) -> ShareCode:
    """Validate and normalize a user-entered sharing code."""
    if value is None or value == "":
        return ShareCode(DEFAULT_SHARE_CODE, int(DEFAULT_SHARE_CODE), True)
    if len(value) > 10 or not value.isascii() or not value.isdecimal():
        raise ShareCodeError("分享代码必须是 1-10 位 ASCII 十进制数字。")

    seed = int(value, 10)
    if seed > MAX_SEED:
        raise ShareCodeError("分享代码超出允许范围。")
    return ShareCode(str(seed), seed, False)


def generate_share_code() -> ShareCode:
    """Generate a six-digit code, excluding the documented default."""
    while True:
        seed = MIN_RANDOM_CODE + secrets.randbelow(MAX_RANDOM_CODE - MIN_RANDOM_CODE + 1)
        if seed != int(DEFAULT_SHARE_CODE):
            return ShareCode(str(seed), seed, False)
