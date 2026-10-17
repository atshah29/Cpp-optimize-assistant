#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    std::uint64_t sum = 0;
    for (unsigned i = 0; i < n; ++i) {
        seed = seed * 1664525u + 1013904223u;
        sum += (seed >> 16) % 1000;
    }
    return sum;
}

