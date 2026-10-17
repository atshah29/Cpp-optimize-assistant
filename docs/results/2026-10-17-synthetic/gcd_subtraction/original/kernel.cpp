#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto a = make_data(n, seed), b = make_data(n, seed + 17);
    std::uint64_t result = 0;
    for (unsigned i = 0; i < n; ++i) {
        unsigned x = a[i] + 1, y = b[i] + 1;
        while (x != y) { if (x > y) x -= y; else y -= x; }
        result += x;
    }
    return result;
}

