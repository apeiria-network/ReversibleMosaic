# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Cython acceleration for V1 neighborhood-swap inner loops.

Loaded lazily and only used when the compiled artifact exists. The reference
implementation in :mod:`reference_v1` remains the specification of record
until the release-blocking probe report freezes V1.

Byte-identity contract: :func:`neighborhood_swap_forward` and its inverse
must produce **exactly** the same output as the pure-Python reference for
every legal ``(pixels, key, radius)`` triple. ``tests/unit/test_optimized_v1.py``
enforces this on Linux/CI; Windows PC dev has no Cython build and falls
back to the reference implementation.
"""

from libc.stdint cimport uint8_t, uint64_t


cdef uint64_t SPLIT_INC = <uint64_t>0x9E3779B97F4A7C15
cdef uint64_t SPLIT_MUL1 = <uint64_t>0xBF58476D1CE4E5B9
cdef uint64_t SPLIT_MUL2 = <uint64_t>0x94D049BB133111EB
cdef uint64_t LOW32 = <uint64_t>0xFFFFFFFF


cdef inline uint64_t splitmix64(uint64_t value) noexcept nogil:
    value += SPLIT_INC
    value = (value ^ (value >> 30)) * SPLIT_MUL1
    value = (value ^ (value >> 27)) * SPLIT_MUL2
    return value ^ (value >> 31)


cdef inline void _swap_pixel(
    uint8_t[:, :, ::1] pixels,
    Py_ssize_t y_a,
    Py_ssize_t x_a,
    Py_ssize_t y_b,
    Py_ssize_t x_b,
) noexcept nogil:
    """Swap two whole pixels in place along all channels."""
    cdef Py_ssize_t channel, channels = pixels.shape[2]
    cdef uint8_t temporary
    for channel in range(channels):
        temporary = pixels[y_a, x_a, channel]
        pixels[y_a, x_a, channel] = pixels[y_b, x_b, channel]
        pixels[y_b, x_b, channel] = temporary


cpdef void neighborhood_swap_forward(
    uint8_t[:, :, ::1] pixels,
    uint64_t key,
    uint64_t radius,
):
    """Forward-scan neighbourhood swap; iterate y=0..H-1, x=0..W-1.

    For each pixel ``i = y*W + x``, derive a modular ``(2R+1)^2`` partner
    ``(yj, xj)`` via SplitMix64 and swap when ``j > i``. Byte-identical to
    :func:`reversible_mosaic.core.algorithm.reference_v1._neighborhood_swap_forward`.
    """
    cdef Py_ssize_t height = pixels.shape[0]
    cdef Py_ssize_t width = pixels.shape[1]
    cdef uint64_t denom = 2 * radius + 1
    cdef uint64_t width_u = <uint64_t>width
    cdef uint64_t height_u = <uint64_t>height
    cdef Py_ssize_t y, x, yj, xj, i, j
    cdef uint64_t offset, dy_u, dx_u
    with nogil:
        for y in range(height):
            for x in range(width):
                i = y * width + x
                offset = splitmix64(key ^ <uint64_t>i)
                dy_u = (offset >> 32) % denom
                dx_u = (offset & LOW32) % denom
                # (y + dy - R) mod H, kept unsigned via (+H) before mod.
                yj = <Py_ssize_t>((<uint64_t>y + dy_u + height_u - radius) % height_u)
                xj = <Py_ssize_t>((<uint64_t>x + dx_u + width_u - radius) % width_u)
                j = yj * width + xj
                if j > i:
                    _swap_pixel(pixels, y, x, yj, xj)


cpdef void neighborhood_swap_inverse(
    uint8_t[:, :, ::1] pixels,
    uint64_t key,
    uint64_t radius,
):
    """Reverse-scan pass; iterate y=H-1..0, x=W-1..0.

    Replays the same set of swap pairs in reverse order. Byte-identical to
    :func:`reversible_mosaic.core.algorithm.reference_v1._neighborhood_swap_inverse`.
    """
    cdef Py_ssize_t height = pixels.shape[0]
    cdef Py_ssize_t width = pixels.shape[1]
    cdef uint64_t denom = 2 * radius + 1
    cdef uint64_t width_u = <uint64_t>width
    cdef uint64_t height_u = <uint64_t>height
    cdef Py_ssize_t y, x, yj, xj, i, j
    cdef uint64_t offset, dy_u, dx_u
    with nogil:
        for y in range(height - 1, -1, -1):
            for x in range(width - 1, -1, -1):
                i = y * width + x
                offset = splitmix64(key ^ <uint64_t>i)
                dy_u = (offset >> 32) % denom
                dx_u = (offset & LOW32) % denom
                yj = <Py_ssize_t>((<uint64_t>y + dy_u + height_u - radius) % height_u)
                xj = <Py_ssize_t>((<uint64_t>x + dx_u + width_u - radius) % width_u)
                j = yj * width + xj
                if j > i:
                    _swap_pixel(pixels, y, x, yj, xj)
