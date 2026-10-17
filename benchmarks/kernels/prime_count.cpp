#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    std::uint64_t result = 0;
    for (unsigned value = 2; value <= n; ++value) {
        bool prime = true;
        for (unsigned divisor = 2; divisor < value; ++divisor)
            if (value % divisor == 0) { prime = false; break; }
        if (prime) result += value + seed % 7;
    }
    return result;
}

