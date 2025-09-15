// === Diagnostics ===
// Avoid explicit destructor definition unless necessary
// Use default copy constructor and assignment operator
// Use const reference in assignment operator
// Use range-based for loop with const reference
// Removed unnecessary endl in operator<<

#include <iostream>
#include <vector>

template<typename T>
class Foo{
    public:
        Foo(size_t size=0 , T initialValue=0){
            test.resize(size, initialValue);
        }

        Foo(const Foo& other) = default;

        Foo& operator=(const Foo& other) = default;

        friend std::ostream& operator<<(std::ostream& os, const Foo& other){
            for (const auto& element : other.test){
                os << element << " ";
            }
            return os;
        }

    private:
        std::vector<T> test;

};

void hello() {
    std::cout << "Hello World!" << std::endl;
}

int add(int a, int b) {
    return a + b;
}

int main() {
    hello();
    std::cout << add(3, 4) << std::endl;
    Foo<double> example1 (5, 2.0);
    Foo<double> example2 = example1;
    std::cout << example1 << " " << example2 << std::endl;
    return 0;
}
