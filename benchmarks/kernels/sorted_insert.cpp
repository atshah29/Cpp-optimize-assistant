#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::vector<std::uint32_t> sorted;
    for (auto value : values) sorted.insert(std::lower_bound(sorted.begin(), sorted.end(), value), value);
    std::uint64_t result = 0;
    for (unsigned i = 0; i < n; ++i) result += std::uint64_t(i + 1) * sorted[i];
    return result;
}

