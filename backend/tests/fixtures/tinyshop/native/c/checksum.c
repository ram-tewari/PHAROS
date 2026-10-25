#include "checksum.h"

#define MOD_ADLER 65521

/* Adler-32 checksum, used for quick integrity checks of order exports. */
uint32_t adler32(const unsigned char *data, size_t len) {
    uint32_t a = 1, b = 0;
    for (size_t i = 0; i < len; ++i) {
        a = (a + data[i]) % MOD_ADLER;
        b = (b + a) % MOD_ADLER;
    }
    return (b << 16) | a;
}
