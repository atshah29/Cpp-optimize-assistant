#include <iostream>
#include <vector>
using namespace std;
template<typename T>
class Foo{
    public:
        Foo(size_t size=0 , T initialValue=0){
            test.resize(size);
            for (auto& elem : test){
                elem+= initialValue;
            }
        }

        ~Foo(){
            test.clear();
        }

        Foo(const Foo& other):
        test(other.test)
        {
        }

        Foo& operator=(Foo& other){
            if(this != &other){
                test.clear();
                test=other.test;
            }

            return *this;
        }

        friend ostream& operator<<(ostream& os, const Foo& other){
            for (auto& element : other.test){
                os << element << " ";
            }
            os << std::endl;
            return os ;
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
    Foo <double> example1 (5, 2.0);
    Foo<double> example2;
    example2 = example1;

    std::cout << example1 << " " << example2 << std::endl;

    return 0;
}
