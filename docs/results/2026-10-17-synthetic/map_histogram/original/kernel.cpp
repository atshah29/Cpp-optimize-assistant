#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::map<std::uint32_t, std::uint64_t> histogram;
    for (auto value : values) histogram[value]++;
    std::uint64_t result = 0;
    for (const auto& item : histogram) result += (item.first + 1) * item.second * item.second;
    return result;
}

