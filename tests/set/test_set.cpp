#include <set>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_set() {
    std::set<int> v;
    BREAK_HERE("empty");

    v.insert(10);
    v.insert(20);
    v.insert(30);
    BREAK_HERE("three_elements");

    v.erase(20);
    BREAK_HERE("after_erase");

    v.clear();
    BREAK_HERE("cleared");
}

int main() {
    test_set();
    return 0;
}
