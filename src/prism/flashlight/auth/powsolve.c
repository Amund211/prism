// Native solver for the sha256-leading-zeros-v1 proof-of-work.
//
// Loaded with ctypes by native_pow.py, which releases the GIL for the whole of
// every call - so solving runs in parallel with the UI instead of taking turns
// with it. Built by build_powsolve.py. Plain C with no dependencies, so the
// library does not depend on the Python version.
//
// A solution is a counter written as SOLUTION_DIGITS zero-padded decimal digits.

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

#if defined(__x86_64__) || defined(_M_X64)
#define HAVE_SHA_NI 1
#include <cpuid.h>
#include <immintrin.h>
#endif

#if defined(__aarch64__) && (defined(__APPLE__) || defined(__linux__))
#define HAVE_ARMV8 1
#include <arm_neon.h>
#if defined(__linux__)
#include <sys/auxv.h>
#endif
#endif

// Bump when the exported functions change. Checked by the loader.
#define ABI_VERSION 1

#define SOLUTION_DIGITS 12
#define MAX_COUNTER 1000000000000ULL

enum { IMPL_PORTABLE = 1, IMPL_SHA_NI = 2, IMPL_ARMV8 = 3 };

typedef void (*compress_fn)(uint32_t state[8], const uint8_t *data, size_t blocks);

static const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

static const uint32_t INITIAL_STATE[8] = {
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
};

#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void compress_portable(uint32_t s[8], const uint8_t *p, size_t blocks) {
    while (blocks--) {
        uint32_t w[64];
        for (int i = 0; i < 16; i++) {
            w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 |
                   (uint32_t)p[4 * i + 2] << 8 | (uint32_t)p[4 * i + 3];
        }
        for (int i = 16; i < 64; i++) {
            uint32_t s0 = ROR(w[i - 15], 7) ^ ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
            uint32_t s1 = ROR(w[i - 2], 17) ^ ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        uint32_t a = s[0], b = s[1], c = s[2], d = s[3];
        uint32_t e = s[4], f = s[5], g = s[6], h = s[7];
        for (int i = 0; i < 64; i++) {
            uint32_t t1 = h + (ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25)) +
                          ((e & f) ^ (~e & g)) + K[i] + w[i];
            uint32_t t2 = (ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22)) +
                          ((a & b) ^ (a & c) ^ (b & c));
            h = g;
            g = f;
            f = e;
            e = d + t1;
            d = c;
            c = b;
            b = a;
            a = t1 + t2;
        }
        s[0] += a;
        s[1] += b;
        s[2] += c;
        s[3] += d;
        s[4] += e;
        s[5] += f;
        s[6] += g;
        s[7] += h;
        p += 64;
    }
}

#ifdef HAVE_SHA_NI
// Intel SHA extensions. Present on AMD Zen and on Intel since about 2019-2021,
// missing on most older Intel desktop CPUs.
static int sha_ni_supported(void) {
    unsigned int a, b, c, d;
    // SSSE3 and SSE4.1 (leaf 1, ecx bits 9 and 19) for the shuffles
    if (!__get_cpuid(1, &a, &b, &c, &d) || !(c & (1u << 9)) || !(c & (1u << 19))) {
        return 0;
    }
    // SHA (leaf 7, ebx bit 29)
    if (!__get_cpuid_count(7, 0, &a, &b, &c, &d)) {
        return 0;
    }
    return (b & (1u << 29)) != 0;
}

// State is kept as ABEF/CDGH, the layout sha256rnds2 works on
__attribute__((target("sha,sse4.1,ssse3")))
static void compress_sha_ni(uint32_t state[8], const uint8_t *data, size_t blocks) {
    const __m128i BSWAP = _mm_set_epi64x(0x0c0d0e0f08090a0bULL, 0x0405060700010203ULL);
    __m128i tmp = _mm_shuffle_epi32(_mm_loadu_si128((const __m128i *)&state[0]), 0xB1);
    __m128i st1 = _mm_shuffle_epi32(_mm_loadu_si128((const __m128i *)&state[4]), 0x1B);
    __m128i st0 = _mm_alignr_epi8(tmp, st1, 8);
    st1 = _mm_blend_epi16(st1, tmp, 0xF0);

// Four rounds with message words w, for round group g
#define SHA_NI_ROUNDS(w, g)                                                              \
    do {                                                                                 \
        __m128i wk = _mm_add_epi32(w, _mm_loadu_si128((const __m128i *)&K[4 * (g)]));    \
        st1 = _mm_sha256rnds2_epu32(st1, st0, wk);                                       \
        st0 = _mm_sha256rnds2_epu32(st0, st1, _mm_shuffle_epi32(wk, 0x0E));              \
    } while (0)

// The next four message words, replacing w0, from the previous sixteen (oldest first)
#define SHA_NI_SCHEDULE(w0, w1, w2, w3)                                                  \
    w0 = _mm_sha256msg2_epu32(                                                           \
        _mm_add_epi32(_mm_sha256msg1_epu32(w0, w1), _mm_alignr_epi8(w3, w2, 4)), w3)

    while (blocks--) {
        __m128i save0 = st0, save1 = st1;
        __m128i w0 = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(data + 0)), BSWAP);
        __m128i w1 = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(data + 16)), BSWAP);
        __m128i w2 = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(data + 32)), BSWAP);
        __m128i w3 = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(data + 48)), BSWAP);
        SHA_NI_ROUNDS(w0, 0);
        SHA_NI_ROUNDS(w1, 1);
        SHA_NI_ROUNDS(w2, 2);
        SHA_NI_ROUNDS(w3, 3);
        for (int g = 4; g < 16; g += 4) {
            SHA_NI_SCHEDULE(w0, w1, w2, w3);
            SHA_NI_ROUNDS(w0, g);
            SHA_NI_SCHEDULE(w1, w2, w3, w0);
            SHA_NI_ROUNDS(w1, g + 1);
            SHA_NI_SCHEDULE(w2, w3, w0, w1);
            SHA_NI_ROUNDS(w2, g + 2);
            SHA_NI_SCHEDULE(w3, w0, w1, w2);
            SHA_NI_ROUNDS(w3, g + 3);
        }
        st0 = _mm_add_epi32(st0, save0);
        st1 = _mm_add_epi32(st1, save1);
        data += 64;
    }

    tmp = _mm_shuffle_epi32(st0, 0x1B);
    st1 = _mm_shuffle_epi32(st1, 0xB1);
    st0 = _mm_blend_epi16(tmp, st1, 0xF0);
    st1 = _mm_alignr_epi8(st1, tmp, 8);
    _mm_storeu_si128((__m128i *)&state[0], st0);
    _mm_storeu_si128((__m128i *)&state[4], st1);
}
#endif

#ifdef HAVE_ARMV8
// ARMv8 cryptography extensions. Every Apple Silicon CPU has them.
static int armv8_supported(void) {
#if defined(__APPLE__)
    return 1;
#else
    return (getauxval(AT_HWCAP) & HWCAP_SHA2) != 0;
#endif
}

__attribute__((target("arch=armv8-a+sha2")))
static void compress_armv8(uint32_t state[8], const uint8_t *data, size_t blocks) {
    uint32x4_t abcd = vld1q_u32(&state[0]);
    uint32x4_t efgh = vld1q_u32(&state[4]);

// Four rounds with message words w, for round group g
#define ARMV8_ROUNDS(w, g)                                                               \
    do {                                                                                 \
        uint32x4_t wk = vaddq_u32(w, vld1q_u32(&K[4 * (g)]));                            \
        uint32x4_t prev_abcd = abcd;                                                     \
        abcd = vsha256hq_u32(abcd, efgh, wk);                                            \
        efgh = vsha256h2q_u32(efgh, prev_abcd, wk);                                      \
    } while (0)

// The next four message words, replacing w0, from the previous sixteen (oldest first)
#define ARMV8_SCHEDULE(w0, w1, w2, w3) w0 = vsha256su1q_u32(vsha256su0q_u32(w0, w1), w2, w3)

    while (blocks--) {
        uint32x4_t save_abcd = abcd, save_efgh = efgh;
        uint32x4_t w0 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(data + 0)));
        uint32x4_t w1 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(data + 16)));
        uint32x4_t w2 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(data + 32)));
        uint32x4_t w3 = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(data + 48)));
        ARMV8_ROUNDS(w0, 0);
        ARMV8_ROUNDS(w1, 1);
        ARMV8_ROUNDS(w2, 2);
        ARMV8_ROUNDS(w3, 3);
        for (int g = 4; g < 16; g += 4) {
            ARMV8_SCHEDULE(w0, w1, w2, w3);
            ARMV8_ROUNDS(w0, g);
            ARMV8_SCHEDULE(w1, w2, w3, w0);
            ARMV8_ROUNDS(w1, g + 1);
            ARMV8_SCHEDULE(w2, w3, w0, w1);
            ARMV8_ROUNDS(w2, g + 2);
            ARMV8_SCHEDULE(w3, w0, w1, w2);
            ARMV8_ROUNDS(w3, g + 3);
        }
        abcd = vaddq_u32(abcd, save_abcd);
        efgh = vaddq_u32(efgh, save_efgh);
        data += 64;
    }

    vst1q_u32(&state[0], abcd);
    vst1q_u32(&state[4], efgh);
}
#endif

// NULL if the implementation is unknown or can't run on this CPU
static compress_fn get_compress(int impl) {
    switch (impl) {
    case IMPL_PORTABLE:
        return compress_portable;
#ifdef HAVE_SHA_NI
    case IMPL_SHA_NI:
        return sha_ni_supported() ? compress_sha_ni : NULL;
#endif
#ifdef HAVE_ARMV8
    case IMPL_ARMV8:
        return armv8_supported() ? compress_armv8 : NULL;
#endif
    default:
        return NULL;
    }
}

// Write the final block(s) for a message of `total_len` bytes whose last
// `tail_len` bytes are in `tail`. Returns the number of blocks (1 or 2).
static size_t pad(uint8_t buf[128], const uint8_t *tail, size_t tail_len, uint64_t total_len) {
    size_t blocks = tail_len + 9 <= 64 ? 1 : 2;
    memset(buf, 0, 128);
    memcpy(buf, tail, tail_len);
    buf[tail_len] = 0x80;
    uint64_t bits = total_len * 8;
    for (int i = 0; i < 8; i++) {
        buf[blocks * 64 - 1 - i] = (uint8_t)(bits >> (8 * i));
    }
    return blocks;
}

EXPORT int pow_abi_version(void) { return ABI_VERSION; }

EXPORT int pow_impl_supported(int impl) { return get_compress(impl) != NULL; }

// SHA-256 of `data`, for testing an implementation. Returns 0, or -1 if the
// implementation is unsupported.
EXPORT int pow_sha256(int impl, const uint8_t *data, size_t len, uint8_t out[32]) {
    compress_fn compress = get_compress(impl);
    if (compress == NULL) {
        return -1;
    }
    uint32_t state[8];
    memcpy(state, INITIAL_STATE, sizeof state);
    compress(state, data, len / 64);
    uint8_t buf[128];
    size_t blocks = pad(buf, data + len / 64 * 64, len % 64, len);
    compress(state, buf, blocks);
    for (int i = 0; i < 8; i++) {
        out[4 * i] = (uint8_t)(state[i] >> 24);
        out[4 * i + 1] = (uint8_t)(state[i] >> 16);
        out[4 * i + 2] = (uint8_t)(state[i] >> 8);
        out[4 * i + 3] = (uint8_t)state[i];
    }
    return 0;
}

// Search counters in [start, end) for the first one where
// SHA-256(prefix || counter) has at least `difficulty` leading zero bits.
// Returns 1 and sets *found, 0 if the range holds no solution, or -1 on bad
// arguments.
EXPORT int pow_solve(int impl, const uint8_t *prefix, size_t len, int difficulty,
                     uint64_t start, uint64_t end, uint64_t *found) {
    compress_fn compress = get_compress(impl);
    if (compress == NULL || difficulty < 0 || difficulty > 32 || start > end ||
        end > MAX_COUNTER) {
        return -1;
    }

    // Midstate: the full blocks of the prefix are the same for every attempt
    uint32_t mid[8];
    memcpy(mid, INITIAL_STATE, sizeof mid);
    compress(mid, prefix, len / 64);

    size_t tail_len = len % 64;
    uint8_t tail[64 + SOLUTION_DIGITS];
    memcpy(tail, prefix + len / 64 * 64, tail_len);
    uint64_t n = start;
    for (int i = SOLUTION_DIGITS - 1; i >= 0; i--) {
        tail[tail_len + i] = (uint8_t)('0' + n % 10);
        n /= 10;
    }
    uint8_t buf[128];
    size_t blocks = pad(buf, tail, tail_len + SOLUTION_DIGITS, len + SOLUTION_DIGITS);
    uint8_t *digits = buf + tail_len;

    // The first state word holds the leading 32 bits of the digest
    uint32_t mask = difficulty == 0 ? 0 : 0xffffffffu << (32 - difficulty);
    for (uint64_t counter = start; counter < end; counter++) {
        uint32_t state[8];
        memcpy(state, mid, sizeof state);
        compress(state, buf, blocks);
        if ((state[0] & mask) == 0) {
            *found = counter;
            return 1;
        }
        // Increment the decimal counter in place
        for (int i = SOLUTION_DIGITS - 1; i >= 0 && ++digits[i] > '9'; i--) {
            digits[i] = '0';
        }
    }
    return 0;
}
