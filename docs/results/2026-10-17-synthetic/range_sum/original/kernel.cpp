#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t result = 0;
    for (unsigned q = 0; q < 1000; ++q) {
        unsigned a = (std::uint64_t(seed) + q * 17u) % n;
        unsigned b = (std::uint64_t(seed) + q * 31u) % n;
        if (a > b) std::swap(a, b);
        for (unsigned i = a; i <= b; ++i) result += values[i];
    }
    return result;
}

