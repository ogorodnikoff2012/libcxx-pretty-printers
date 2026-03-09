#include <optional>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_optional() {
    std::optional<int> v;
    BREAK_HERE("empty");

    v = 42;
    BREAK_HERE("with_value");

    v.reset();
    BREAK_HERE("after_reset");
}

int main() {
    test_optional();
    return 0;
}
