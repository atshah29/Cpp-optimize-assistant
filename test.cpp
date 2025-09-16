#include <iostream>
#include "math_utils.h"

int main() {
    std::cout << "Hello from multi-file project!" << std::endl;

    int a = 10, b = 20;
    std::cout << "Add: " << add(a, b) << std::endl;
    std::cout << "Multiply: " << multiply(a, b) << std::endl;

    return 0;
}
