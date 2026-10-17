#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n * n, seed);
    std::vector<std::uint32_t> transposed(n * n);
    for (unsigned row = 0; row < n; ++row)
        for (unsigned col = 0; col < n; ++col)
            transposed[col * n + row] = values[row * n + col];
    std::uint64_t result = 0;
    for (unsigned i = 0; i < n * n; ++i) result += std::uint64_t(transposed[i]) * (i % 97 + 1);
    return result;
}

