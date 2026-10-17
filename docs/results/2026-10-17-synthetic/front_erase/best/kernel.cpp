#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t total = std::accumulate(values.begin(), values.end(), std::uint64_t(0));
    return total;
}

