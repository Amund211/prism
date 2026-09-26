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

// Bump when the exported functions change. Checked by the loader.
#define ABI_VERSION 1

#define SOLUTION_DIGITS 12
#define MAX_COUNTER 1000000000000ULL

enum { IMPL_PORTABLE = 1 };

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

static compress_fn get_compress(int impl) {
    switch (impl) {
    case IMPL_PORTABLE:
        return compress_portable;
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
