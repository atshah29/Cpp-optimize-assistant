#include "iostream"
#include "math_utils.h"

//Using std::endl can lead to performance issues due to flushing the buffer after each insertion. Replaced with '\n' for better performance.
//Consider using a single std::cout statement for all output to reduce the number of buffer flushes.
//Functions add and multiply have minimal overhead and are unlikely to benefit from further optimization.


int add(int x, int y) {
    return x + y;
}

int multiply(int x, int y) {
    return x * y;
}

int main() {
    std::cout << "Hello from multi-file project!\n";

    int a = 10, b = 20;
    std::cout << "Add: " << add(a, b) << '\n';
    std::cout << "Multiply: " << multiply(a, b) << '\n';

    return 0;
}
