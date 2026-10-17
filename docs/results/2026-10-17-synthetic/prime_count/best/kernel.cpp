#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    std::uint64_t result = 0;
    const std::uint32_t add = seed % 7;
    for (std::uint32_t value = 2; value <= n; ++value) {
        bool prime = true;
        for (std::uint32_t divisor = 2; divisor * divisor <= value; ++divisor) {
            if (value % divisor == 0) { prime = false; break; }
        }
        if (prime) result += value + add;
    }
    return result;
}

