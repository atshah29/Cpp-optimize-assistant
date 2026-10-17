#include "common.hpp"
#include <array>
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    // Presence bitmap for values in the range [0,999]
    std::array<std::uint8_t, 1000> present{};
    // Generate values and mark presence
    std::uint32_t cur = seed;
    for (std::uint32_t i = 0; i < n; ++i) {
        cur = cur * 1664525u + 1013904223u;
        present[(cur >> 16) % 1000] = 1;
    }
    // Generate queries and count matches
    std::uint64_t found = 0;
    cur = seed + 17;
    for (std::uint32_t i = 0; i < n; ++i) {
        cur = cur * 1664525u + 1013904223u;
        std::uint32_t q = (cur >> 16) % 1000;
        found += present[q] != 0;
    }
    return found;
}

