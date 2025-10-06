#include "iostream"
#include "math_utils.h"

//Consider using const for variables that do not change.
//Reduced number of std::endl for better performance.


int add(int x, int y) {
    return x + y;
}

int multiply(int x, int y) {
    return x * y;
}

int main() {
    const int a = 10, b = 20;
    std::cout << "Hello from multi-file project!\n";
    std::cout << "Add: " << add(a, b) << "\n";
    std::cout << "Multiply: " << multiply(a, b) << "\n";
    return 0;
}

// Optimized by FastAPI