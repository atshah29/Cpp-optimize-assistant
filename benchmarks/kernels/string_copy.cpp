#include "common.hpp"
static unsigned char at_copy(std::string text, unsigned i) { return text[i]; }
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::string text;
    for (auto value : values) text.push_back(char('a' + value % 26));
    std::uint64_t result = 0;
    for (unsigned i = 0; i < n; i += 8) result += at_copy(text, i);
    return result;
}

