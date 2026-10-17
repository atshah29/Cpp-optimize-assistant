#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t total = 0;
    while (!values.empty()) {
        total += values.front();
        values.erase(values.begin());
    }
    return total;
}

