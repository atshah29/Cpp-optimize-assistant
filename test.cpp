#include <iostream>
#include <vector>

void hello() {
    std::cout << "Hello World!" << std::endl;
}

int add(int a, int b) {
    return a + b;
}

int main() {
    hello();
    std::cout << add(3, 4) << std::endl;
    return 0;
}
