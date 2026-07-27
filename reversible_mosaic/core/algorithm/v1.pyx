# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Cython acceleration candidate for V1 inner loops.

Loaded lazily and only used when the compiled artifact exists. The reference
implementation in ``reference_v1`` remains the specification of record until
the release-blocking probe report freezes V1.
"""

from libc.stdint cimport uint8_t, uint64_t


cdef extern from *:
    """
    static inline uint64_t rm_mul_hi_64(uint64_t a, uint64_t b) {
        return (uint64_t)(((__uint128_t)a * (__uint128_t)b) >> 64);
    }
    """
    uint64_t rm_mul_hi_64(uint64_t a, uint64_t b) nogil


cdef uint64_t SPLIT_INC = <uint64_t>0x9E3779B97F4A7C15
cdef uint64_t SPLIT_MUL1 = <uint64_t>0xBF58476D1CE4E5B9
cdef uint64_t SPLIT_MUL2 = <uint64_t>0x94D049BB133111EB
cdef uint64_t IV_INDEX = <uint64_t>0xFFFFFFFFFFFFFFFF


cdef inline uint64_t splitmix64(uint64_t value) noexcept nogil:
    value += SPLIT_INC
    value = (value ^ (value >> 30)) * SPLIT_MUL1
    value = (value ^ (value >> 27)) * SPLIT_MUL2
    return value ^ (value >> 31)


cpdef void lift_forward(uint8_t[:, ::1] pixels, uint64_t key):
    cdef Py_ssize_t index, length = pixels.shape[0]
    cdef uint64_t value
    cdef unsigned int r, g, b, m0, m1, m2
    with nogil:
        for index in range(length):
            value = splitmix64(key ^ <uint64_t>index)
            m0 = value & 255u
            m1 = (value >> 8) & 255u
            m2 = (value >> 16) & 255u
            r = pixels[index, 0]
            g = pixels[index, 1]
            b = pixels[index, 2]
            r = (r + 3u * g + 5u * b + m0) & 255u
            g = (g + 5u * b + 7u * r + m1) & 255u
            b = (b + 7u * r + 3u * g + m2) & 255u
            pixels[index, 0] = <uint8_t>r
            pixels[index, 1] = <uint8_t>g
            pixels[index, 2] = <uint8_t>b


cpdef void lift_inverse(uint8_t[:, ::1] pixels, uint64_t key):
    cdef Py_ssize_t index, length = pixels.shape[0]
    cdef uint64_t value
    cdef int r, g, b, m0, m1, m2
    with nogil:
        for index in range(length):
            value = splitmix64(key ^ <uint64_t>index)
            m0 = <int>(value & 255u)
            m1 = <int>((value >> 8) & 255u)
            m2 = <int>((value >> 16) & 255u)
            r = pixels[index, 0]
            g = pixels[index, 1]
            b = pixels[index, 2]
            b = (b - 7 * r - 3 * g - m2) & 255
            g = (g - 5 * b - 7 * r - m1) & 255
            r = (r - 3 * g - 5 * b - m0) & 255
            pixels[index, 0] = <uint8_t>r
            pixels[index, 1] = <uint8_t>g
            pixels[index, 2] = <uint8_t>b


cpdef void permute_forward(uint8_t[:, ::1] pixels, uint64_t key):
    cdef Py_ssize_t index, other, channel, channels = pixels.shape[1]
    cdef uint64_t random_word
    cdef uint8_t temporary
    with nogil:
        for index in range(pixels.shape[0] - 1, 0, -1):
            random_word = splitmix64(key ^ <uint64_t>index)
            other = <Py_ssize_t>rm_mul_hi_64(random_word, <uint64_t>(index + 1))
            for channel in range(channels):
                temporary = pixels[index, channel]
                pixels[index, channel] = pixels[other, channel]
                pixels[other, channel] = temporary


cpdef void permute_inverse(uint8_t[:, ::1] pixels, uint64_t key):
    cdef Py_ssize_t index, other, channel, channels = pixels.shape[1]
    cdef uint64_t random_word
    cdef uint8_t temporary
    with nogil:
        for index in range(1, pixels.shape[0]):
            random_word = splitmix64(key ^ <uint64_t>index)
            other = <Py_ssize_t>rm_mul_hi_64(random_word, <uint64_t>(index + 1))
            for channel in range(channels):
                temporary = pixels[index, channel]
                pixels[index, channel] = pixels[other, channel]
                pixels[other, channel] = temporary


cdef inline void _diffuse_masks(uint64_t key, uint64_t index, unsigned int* masks) noexcept nogil:
    cdef uint64_t value = splitmix64(key ^ index)
    masks[0] = value & 255u
    masks[1] = (value >> 8) & 255u
    masks[2] = (value >> 16) & 255u


cpdef void diffuse_forward(uint8_t[:, ::1] pixels, uint64_t key, bint reverse):
    cdef Py_ssize_t index, length = pixels.shape[0]
    cdef unsigned int previous[3]
    cdef unsigned int mask[3]
    cdef unsigned int source[3]
    cdef unsigned int output[3]
    with nogil:
        _diffuse_masks(key, IV_INDEX, previous)
        if reverse:
            for index in range(length - 1, -1, -1):
                _diffuse_masks(key, <uint64_t>index, mask)
                source[0] = pixels[index, 0]
                source[1] = pixels[index, 1]
                source[2] = pixels[index, 2]
                output[0] = (source[0] + previous[1] + mask[0]) & 255u
                output[1] = (source[1] + previous[2] + mask[1]) & 255u
                output[2] = (source[2] + previous[0] + mask[2]) & 255u
                pixels[index, 0] = <uint8_t>output[0]
                pixels[index, 1] = <uint8_t>output[1]
                pixels[index, 2] = <uint8_t>output[2]
                previous[0] = output[0]
                previous[1] = output[1]
                previous[2] = output[2]
        else:
            for index in range(length):
                _diffuse_masks(key, <uint64_t>index, mask)
                source[0] = pixels[index, 0]
                source[1] = pixels[index, 1]
                source[2] = pixels[index, 2]
                output[0] = (source[0] + previous[1] + mask[0]) & 255u
                output[1] = (source[1] + previous[2] + mask[1]) & 255u
                output[2] = (source[2] + previous[0] + mask[2]) & 255u
                pixels[index, 0] = <uint8_t>output[0]
                pixels[index, 1] = <uint8_t>output[1]
                pixels[index, 2] = <uint8_t>output[2]
                previous[0] = output[0]
                previous[1] = output[1]
                previous[2] = output[2]


cpdef void diffuse_inverse(uint8_t[:, ::1] pixels, uint64_t key, bint reverse):
    cdef Py_ssize_t index, length = pixels.shape[0]
    cdef unsigned int previous[3]
    cdef unsigned int mask[3]
    cdef unsigned int encoded[3]
    with nogil:
        _diffuse_masks(key, IV_INDEX, previous)
        if reverse:
            for index in range(length - 1, -1, -1):
                _diffuse_masks(key, <uint64_t>index, mask)
                encoded[0] = pixels[index, 0]
                encoded[1] = pixels[index, 1]
                encoded[2] = pixels[index, 2]
                pixels[index, 0] = <uint8_t>((encoded[0] - previous[1] - mask[0]) & 255u)
                pixels[index, 1] = <uint8_t>((encoded[1] - previous[2] - mask[1]) & 255u)
                pixels[index, 2] = <uint8_t>((encoded[2] - previous[0] - mask[2]) & 255u)
                previous[0] = encoded[0]
                previous[1] = encoded[1]
                previous[2] = encoded[2]
        else:
            for index in range(length):
                _diffuse_masks(key, <uint64_t>index, mask)
                encoded[0] = pixels[index, 0]
                encoded[1] = pixels[index, 1]
                encoded[2] = pixels[index, 2]
                pixels[index, 0] = <uint8_t>((encoded[0] - previous[1] - mask[0]) & 255u)
                pixels[index, 1] = <uint8_t>((encoded[1] - previous[2] - mask[1]) & 255u)
                pixels[index, 2] = <uint8_t>((encoded[2] - previous[0] - mask[2]) & 255u)
                previous[0] = encoded[0]
                previous[1] = encoded[1]
                previous[2] = encoded[2]
