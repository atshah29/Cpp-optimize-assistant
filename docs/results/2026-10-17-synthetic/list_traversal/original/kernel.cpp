#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::list<std::uint32_t> linked(values.begin(), values.end());
    std::uint64_t result = 0;
    for (unsigned pass = 0; pass < 16; ++pass)
        for (auto value : linked) result += value + pass;
    return result;
}

