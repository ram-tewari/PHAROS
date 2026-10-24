//! Native helpers for tinyshop.

use std::fmt;

/// CRC-32 (IEEE) checksum used to verify uploaded product images.
pub fn crc32(data: &[u8]) -> u32 {
    let mut crc: u32 = 0xFFFF_FFFF;
    for &byte in data {
        crc ^= byte as u32;
        for _ in 0..8 {
            let mask = (!(crc & 1)).wrapping_add(1);
            crc = (crc >> 1) ^ (0xEDB8_8320 & mask);
        }
    }
    !crc
}

/// A money amount in integer cents.
pub struct Cents(pub i64);

impl fmt::Display for Cents {
    /// Format cents as dollars, e.g. `1250` -> `$12.50`.
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "${}.{:02}", self.0 / 100, self.0 % 100)
    }
}
