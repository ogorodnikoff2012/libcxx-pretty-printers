#include <deque>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_deque() {
    std::deque<int> v;
    BREAK_HERE("empty");

    v.push_back(10);
    v.push_back(20);
    v.push_back(30);
    BREAK_HERE("after_push_back");

    v.push_front(5);
    BREAK_HERE("after_push_front");

    v.pop_back();
    BREAK_HERE("after_pop_back");

    v.pop_front();
    BREAK_HERE("after_pop_front");

    v = {100, 200, 300, 400, 500};
    BREAK_HERE("after_assign");

    v.clear();
    BREAK_HERE("cleared");
}

int main() {
    test_deque();
    return 0;
}
