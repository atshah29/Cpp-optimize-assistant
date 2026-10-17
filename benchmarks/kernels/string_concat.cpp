#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::string text;
    for (auto value : values) text = text + char('a' + value % 26);
    std::uint64_t result = 0;
    for (unsigned i = 0; i < text.size(); ++i) result += std::uint64_t(text[i]) * (i % 17 + 1);
    return result;
}

