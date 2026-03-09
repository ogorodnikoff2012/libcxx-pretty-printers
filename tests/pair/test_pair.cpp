#include <utility>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_pair_int_double() {
    std::pair<int, double> v(42, 3.14);
    BREAK_HERE("int_double");
}

void test_pair_int_int() {
    std::pair<int, int> v(1, 2);
    BREAK_HERE("int_int");
}

int main() {
    test_pair_int_double();
    test_pair_int_int();
    return 0;
}
