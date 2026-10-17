#include "calculate.hpp"
#include <iostream>
int main() {
    int value;
    if (!(std::cin >> value) || value < -1000 || value > 1000) return 1;
    std::cout << calculate(value) << '\n';
}
