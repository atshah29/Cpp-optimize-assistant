#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>

// Deliberately copies a large array on every call. The output makes the work observable.
std::uint64_t sum_values(std::vector<std::uint64_t> values) {
    std::uint64_t total = 0;
    for (auto value : values) total += value;
    return total;
}

int main(int argc, char** argv) {
    const int n = argc > 1 ? std::atoi(argv[1]) : 1000000;
    if (n < 1 || n > 10000000) return 1;
    std::vector<std::uint64_t> values(n);
    for (int i = 0; i < n; ++i) values[i] = static_cast<std::uint64_t>(i % 997);
    std::uint64_t checksum = 0;
    for (int round = 0; round < 200; ++round) {
        values[round % n] += 1;
        checksum += sum_values(values);
    }
    std::cout << checksum << '\n';
}
