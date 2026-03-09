#include <unordered_map>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_unordered_map() {
    std::unordered_map<int, int> v;
    BREAK_HERE("empty");

    v[1] = 10;
    BREAK_HERE("one_element");

    v.clear();
    BREAK_HERE("cleared");
}

int main() {
    test_unordered_map();
    return 0;
}
