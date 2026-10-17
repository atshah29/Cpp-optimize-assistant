#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <list>
#include <map>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

inline std::vector<std::uint32_t> make_data(std::uint32_t n, std::uint32_t seed) {
    std::vector<std::uint32_t> values;
    values.reserve(n);
    for (std::uint32_t i = 0; i < n; ++i) {
        seed = seed * 1664525u + 1013904223u;
        values.push_back((seed >> 16) % 1000);
    }
    return values;
}
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed);
