#ifndef TINYSHOP_CHECKSUM_H
#define TINYSHOP_CHECKSUM_H

#include <stddef.h>
#include <stdint.h>

uint32_t adler32(const unsigned char *data, size_t len);

#endif
