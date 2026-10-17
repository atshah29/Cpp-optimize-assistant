#include "common.hpp"
#include <iostream>
#include <stdexcept>

// Immutable workload driver. Seed changes each round; checksums make results observable.
int main(int argc, char** argv) {
    if (argc != 4) return 1;
    try {
        const auto n = std::stoul(argv[1]);
        const auto rounds = std::stoul(argv[2]);
        const auto seed = std::stoul(argv[3]);
        if (n > 10000000 || rounds > 1000000 || seed > 1000000000) return 1;
        std::uint64_t checksum = 0;
        for (unsigned long i = 0; i < rounds; ++i)
            checksum += n ? kernel(n, seed + i) : 0;
        std::cout << checksum << '\n';
    } catch (const std::exception&) { return 1; }
}
