#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    std::uint64_t result = 0;
    char window[4];
    std::size_t wsize = 0;
    for (std::uint32_t i = 0; i < n; ++i) {
        seed = seed * 1664525u + 1013904223u;
        std::uint32_t value = (seed >> 16) % 1000;
        char c = static_cast<char>('a' + (value % 4));
        if (wsize < 4) {
            window[wsize++] = c;
            if (wsize == 4 && std::equal(window, window + 4, "abcd")) ++result;
        } else {
            window[0] = window[1];
            window[1] = window[2];
            window[2] = window[3];
            window[3] = c;
            if (std::equal(window, window + 4, "abcd")) ++result;
        }
    }
    return result;
}

