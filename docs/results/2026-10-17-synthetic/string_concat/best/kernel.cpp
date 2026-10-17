#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t result = 0;
    for (std::size_t i = 0; i < values.size(); ++i) {
        char c = static_cast<char>('a' + values[i] % 26);
        result += static_cast<std::uint64_t>(c) * (i % 17 + 1);
    }
    return result;
}

