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
    rounds=st.sampled_from([1, 5]),
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
