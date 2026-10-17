#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    std::vector<std::uint32_t> values;
    for (unsigned i = 0; i < n; ++i) {
        seed = seed * 1664525u + 1013904223u;
        values.push_back((seed >> 16) % 1000);
    }
    return std::accumulate(values.begin(), values.end(), std::uint64_t{0});
}

