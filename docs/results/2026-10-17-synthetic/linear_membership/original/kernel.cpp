#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    auto queries = make_data(n, seed + 17);
    std::uint64_t found = 0;
    for (auto query : queries)
        found += std::find(values.begin(), values.end(), query) != values.end();
    return found;
}

