#include "common.hpp"
static std::uint64_t fib(unsigned n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
std::uint64_t kernel(std::uint32_t n, std::uint32_t seed) {
    return fib(std::min(n, 40u)) + seed % 97;
}

