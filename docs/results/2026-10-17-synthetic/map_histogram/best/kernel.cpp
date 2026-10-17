#include "common.hpp"
#include <unordered_map>
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    std::unordered_map<std::uint32_t, std::uint64_t> histogram;
    histogram.reserve(n);
    for (std::uint32_t i = 0; i < n; ++i) {
        seed = seed * 1664525u + 1013904223u;
        std::uint32_t value = (seed >> 16) % 1000;
        histogram[value]++;
    }
    std::uint64_t result = 0;
    for (const auto& item : histogram) result += (item.first + 1) * item.second * item.second;
    return result;
}

