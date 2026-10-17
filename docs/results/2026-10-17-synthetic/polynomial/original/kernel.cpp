#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t result = 0;
    for (auto value : values) {
        const std::uint64_t x = value % 10;
        for (unsigned k = 0; k < 8; ++k) {
            std::uint64_t power = 1;
            for (unsigned j = 0; j < k; ++j) power *= x;
            result += (k + 1) * power;
        }
    }
    return result;
}

