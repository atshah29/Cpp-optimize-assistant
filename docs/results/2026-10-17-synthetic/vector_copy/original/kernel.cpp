#include "common.hpp"
static std::uint64_t sum_copy(std::vector<std::uint32_t> values) {
    return std::accumulate(values.begin(), values.end(), std::uint64_t{0});
}
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t total = 0;
    for (unsigned i = 0; i < 16; ++i) {
        values[i % n] += i;
        total += sum_copy(values);
    }
    return total;
}

