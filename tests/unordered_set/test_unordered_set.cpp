#include <unordered_set>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_unordered_set() {
    std::unordered_set<int> v;
    BREAK_HERE("empty");

    v.insert(42);
    BREAK_HERE("one_element");

    v.clear();
    BREAK_HERE("cleared");
}

int main() {
    test_unordered_set();
    return 0;
}
