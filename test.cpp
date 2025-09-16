#include <iostream>
#include <vector>
#include <string>
#include <numeric>
#include <algorithm>

enum Color {
    Red,
    Green,
    Blue
};

class Stats {
public:
    Stats(const std::vector<int>& data) : numbers(data) {}

    double average() const {
        if (numbers.empty()) return 0.0;
        return std::accumulate(numbers.begin(), numbers.end(), 0.0) / numbers.size();
    }

    int max_value() const {
        return *std::max_element(numbers.begin(), numbers.end());
    }

    int min_value() const {
        return *std::min_element(numbers.begin(), numbers.end());
    }

    void print() const {
        std::cout << "Avg: " << average()
                  << " | Max: " << max_value()
                  << " | Min: " << min_value() << std::endl;
    }

private:
    std::vector<int> numbers;
};

int square(int x) {
    return x * x;
}

void hello(const std::string& name, Color c) {
    std::cout << "Hello, " << name << "! Your favorite color is ";
    switch (c) {
        case Red: std::cout << "Red"; break;
        case Green: std::cout << "Green"; break;
        case Blue: std::cout << "Blue"; break;
    }
    std::cout << std::endl;
}

int main() {
    hello("Aadesh", Blue);

    std::vector<int> nums = {1, 2, 3, 4, 5};
    Stats s(nums);
    s.print();

    std::cout << "Square of 7: " << square(7) << std::endl;

    return 0;
}
