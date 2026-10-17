#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    const unsigned width = std::min(n, 128u);
    std::uint64_t result = 0;
    for (unsigned i = 0; i + width <= n; ++i)
        for (unsigned j = 0; j < width; ++j) result += values[i + j];
    return result;
}

