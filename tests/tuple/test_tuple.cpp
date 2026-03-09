#include <tuple>
#include <string>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_empty_tuple() {
    std::tuple<> v;
    BREAK_HERE("empty_tuple");
}

void test_single_tuple() {
    std::tuple<int> v(42);
    BREAK_HERE("single");
}

void test_triple_tuple() {
    std::tuple<int, double, std::string> v(1, 3.14, "hello");
    BREAK_HERE("triple");
}

int main() {
    test_empty_tuple();
    test_single_tuple();
    test_triple_tuple();
    return 0;
}
