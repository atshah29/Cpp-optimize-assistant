#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t result = 0;
    for (auto value : values) {
        if (value == 0) {
            result += static_cast<unsigned char>('0');
        } else {
            while (value > 0) {
                result += static_cast<unsigned char>('0' + (value % 10));
                value /= 10;
            }
        }
    }
    return result;
}

