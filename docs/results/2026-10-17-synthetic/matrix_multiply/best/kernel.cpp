#include "common.hpp"
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    auto a = make_data(n * n, seed), b = make_data(n * n, seed + 17);
    std::vector<std::uint64_t> c(n * n, 0);
    for (unsigned i = 0; i < n; ++i) {
        for (unsigned k = 0; k < n; ++k) {
            std::uint64_t aik = a[i * n + k];
            for (unsigned j = 0; j < n; ++j) {
                c[i * n + j] += aik * b[k * n + j];
            }
        }
    }
    return std::accumulate(c.begin(), c.end(), std::uint64_t{0});
}

