#include <memory>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_unique_ptr() {
    std::unique_ptr<int> v;
    BREAK_HERE("null");

    v = std::make_unique<int>(42);
    BREAK_HERE("valid");

    v.reset();
    BREAK_HERE("after_reset");
}

int main() {
    test_unique_ptr();
    return 0;
}
