#include <bitset>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_bitset() {
    std::bitset<8> v;
    BREAK_HERE("all_zero");

    v.set(0);
    v.set(3);
    v.set(7);
    BREAK_HERE("some_bits");

    v.set();
    BREAK_HERE("all_set");

    v.reset();
    BREAK_HERE("after_reset");
}

int main() {
    test_bitset();
    return 0;
}
