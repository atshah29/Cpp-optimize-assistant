#include "common.hpp"
#include <numeric>
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    std::uint64_t result = 0;
    std::uint32_t s1 = seed;
    std::uint32_t s2 = seed + 17;
    for (unsigned i = 0; i < n; ++i) {
        s1 = s1 * 1664525u + 1013904223u;
        unsigned x = ((s1 >> 16) % 1000) + 1;
        s2 = s2 * 1664525u + 1013904223u;
        unsigned y = ((s2 >> 16) % 1000) + 1;
        result += std::gcd(x, y);
    }
    return result;
}
