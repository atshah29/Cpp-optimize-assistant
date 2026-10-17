#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    // Initial sum of the generated data
    std::uint64_t sum = std::accumulate(values.begin(), values.end(), std::uint64_t{0});
    std::uint64_t total = 0;
    for (unsigned i = 0; i < 16; ++i) {
        values[i % n] += i;
        sum += i; // update sum with the increment applied to one element
        total += sum;
    }
    return total;
}

