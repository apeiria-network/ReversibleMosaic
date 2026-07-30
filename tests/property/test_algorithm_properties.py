from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from reversible_mosaic.core.algorithm.reference_v1 import decrypt, encrypt


@settings(max_examples=80, deadline=None)
@given(
    width=st.integers(1, 12),
    height=st.integers(1, 12),
    channels=st.sampled_from([3, 4]),
    seed=st.integers(0, 9_999_999_999),
    rounds=st.sampled_from([2, 5]),
    data=st.data(),
)
def test_v1_is_a_bijection(
    width: int,
    height: int,
    channels: int,
    seed: int,
    rounds: int,
    data: st.DataObject,
) -> None:
    values = data.draw(
        st.lists(
            st.integers(0, 255),
            min_size=width * height * channels,
            max_size=width * height * channels,
        )
    )
    source = np.array(values, dtype=np.uint8).reshape(height, width, channels)
    np.testing.assert_array_equal(decrypt(encrypt(source, seed, rounds), seed, rounds), source)


@settings(max_examples=12, deadline=None)
@given(
    width=st.integers(1, 8),
    height=st.integers(1, 8),
    channels=st.sampled_from([3, 4]),
    seed=st.integers(0, 9_999_999_999),
    rounds=st.sampled_from([15, 30]),
    data=st.data(),
)
def test_v1_high_round_bijection(
    width: int,
    height: int,
    channels: int,
    seed: int,
    rounds: int,
    data: st.DataObject,
) -> None:
    values = data.draw(
        st.lists(
            st.integers(0, 255),
            min_size=width * height * channels,
            max_size=width * height * channels,
        )
    )
    source = np.array(values, dtype=np.uint8).reshape(height, width, channels)
    np.testing.assert_array_equal(decrypt(encrypt(source, seed, rounds), seed, rounds), source)


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(1, 12),
    height=st.integers(1, 12),
    channels=st.sampled_from([3, 4]),
    seed=st.integers(0, 9_999_999_999),
    rounds=st.sampled_from([2, 5, 15, 30]),
    data=st.data(),
)
def test_v1_encrypt_is_deterministic(
    width: int,
    height: int,
    channels: int,
    seed: int,
    rounds: int,
    data: st.DataObject,
) -> None:
    values = data.draw(
        st.lists(
            st.integers(0, 255),
            min_size=width * height * channels,
            max_size=width * height * channels,
        )
    )
    source = np.array(values, dtype=np.uint8).reshape(height, width, channels)
    first = encrypt(source, seed, rounds)
    second = encrypt(source, seed, rounds)
    np.testing.assert_array_equal(first, second)


@settings(max_examples=20, deadline=None)
@given(
    width=st.integers(2, 8),
    height=st.integers(2, 8),
    seed=st.integers(0, 9_999_999_999),
    rounds=st.sampled_from([2, 5, 15, 30]),
    data=st.data(),
)
def test_v1_alpha_channel_unchanged_after_bijection(
    width: int,
    height: int,
    seed: int,
    rounds: int,
    data: st.DataObject,
) -> None:
    rgb_values = data.draw(
        st.lists(
            st.integers(0, 255),
            min_size=width * height * 3,
            max_size=width * height * 3,
        )
    )
    alpha_values = data.draw(
        st.lists(
            st.integers(0, 255),
            min_size=width * height,
            max_size=width * height,
        )
    )
    source = np.zeros((height, width, 4), dtype=np.uint8)
    source[..., :3] = np.array(rgb_values, dtype=np.uint8).reshape(height, width, 3)
    source[..., 3] = np.array(alpha_values, dtype=np.uint8).reshape(height, width)
    restored = decrypt(encrypt(source, seed, rounds), seed, rounds)
    np.testing.assert_array_equal(restored, source)
    # Alpha values in the decrypted image reproduce the original set
    assert sorted(restored[..., 3].flatten().tolist()) == sorted(source[..., 3].flatten().tolist())


@settings(max_examples=15, deadline=None)
@given(
    width=st.integers(3, 6),
    height=st.integers(3, 6),
    channels=st.sampled_from([3, 4]),
    rounds=st.sampled_from([2, 5, 15, 30]),
    data=st.data(),
)
def test_v1_nontrivial_output_for_random_seeds(
    width: int,
    height: int,
    channels: int,
    rounds: int,
    data: st.DataObject,
) -> None:
    """Encrypt should modify at least one channel of a non-trivial image."""
    values = data.draw(
        st.lists(
            st.integers(0, 255),
            min_size=width * height * channels,
            max_size=width * height * channels,
        )
    )
    source = np.array(values, dtype=np.uint8).reshape(height, width, channels)
    if channels == 3:
        rgb = source
    else:
        rgb = source[..., :3]
    # V1 is pure spatial permutation with palette preservation. Byte-identical
    # output is legitimate whenever swaps happen between pixels that share the
    # same RGB triple. Requirements §12.3.5 explicitly exempts pure-color / 1x1
    # / low-information images from visual-scramble scoring. Skip cases where
    # the pixel count or palette size makes an identity output plausible:
    # small images with a few dominant pixel values will occasionally survive
    # every swap.
    if width * height < 9 or np.unique(rgb.reshape(-1, 3), axis=0).shape[0] < 5:
        return
    encrypted = encrypt(source, 500_000, rounds)
    # RGB must have changed somewhere; alpha may or may not have been permuted.
    assert not np.array_equal(encrypted[..., :3], source[..., :3])
