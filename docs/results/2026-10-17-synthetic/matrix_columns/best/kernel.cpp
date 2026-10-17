#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n * n, seed);
    std::uint64_t result = 0;
    for (unsigned row = 0; row < n; ++row)
        for (unsigned col = 0; col < n; ++col)
            result += std::uint64_t(values[row * n + col]) * (col + 1);
    return result;
}

