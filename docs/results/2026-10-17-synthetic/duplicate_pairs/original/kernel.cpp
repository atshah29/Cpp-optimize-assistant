#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t pairs = 0;
    for (unsigned i = 0; i < n; ++i)
        for (unsigned j = i + 1; j < n; ++j)
            pairs += values[i] == values[j];
    return pairs;
}

