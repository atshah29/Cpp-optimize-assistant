#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto values = make_data(n, seed);
    std::uint64_t result = 0;
    for (auto value : values) {
        std::ostringstream out;
        out << value;
        for (auto ch : out.str()) result += static_cast<unsigned char>(ch);
    }
    return result;
}

