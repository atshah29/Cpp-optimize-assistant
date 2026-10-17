#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t result = 0;
    for (unsigned pass = 0; pass < 16; ++pass)
        for (auto value : values) result += value + pass;
    return result;
}

