#include <vector>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_vector_int() {
    std::vector<int> v;
    BREAK_HERE("empty");

    v.push_back(10);
    BREAK_HERE("push_back_one");

    v.push_back(20);
    v.push_back(30);
    BREAK_HERE("push_back_three");

    v.pop_back();
    BREAK_HERE("after_pop_back");

    v = {100, 200, 300, 400, 500};
    BREAK_HERE("after_assign");

    v.reserve(100);
    BREAK_HERE("after_reserve");

    v.shrink_to_fit();
    BREAK_HERE("after_shrink_to_fit");

    // Trigger reallocation: reset to zero capacity, then grow past it
    v.clear();
    v.shrink_to_fit();
    BREAK_HERE("cleared");

    v.push_back(1);
    v.push_back(2);
    BREAK_HERE("growing");

    v.push_back(3);
    v.push_back(4);
    v.push_back(5);
    BREAK_HERE("after_realloc");
}

int main() {
    test_vector_int();
    return 0;
}
