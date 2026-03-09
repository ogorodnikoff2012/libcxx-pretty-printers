#include <map>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_map() {
    std::map<int, int> v;
    BREAK_HERE("empty");

    v[1] = 10;
    v[2] = 20;
    v[3] = 30;
    BREAK_HERE("three_elements");

    v.erase(2);
    BREAK_HERE("after_erase");

    v.clear();
    BREAK_HERE("cleared");
}

int main() {
    test_map();
    return 0;
}
