#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::string text;
    for (auto value : values) text.push_back(char('a' + value % 4));
    std::uint64_t result = 0;
    for (unsigned i = 0; i + 4 <= text.size(); ++i)
        if (text.substr(i, 4) == "abcd") result++;
    return result;
}

