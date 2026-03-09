#include <forward_list>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_forward_list() {
    std::forward_list<int> v;
    BREAK_HERE("empty");

    v.push_front(30);
    v.push_front(20);
    v.push_front(10);
    BREAK_HERE("after_push_front");

    v.pop_front();
    BREAK_HERE("after_pop_front");

    v = {100, 200, 300};
    BREAK_HERE("after_assign");

    v.clear();
    BREAK_HERE("cleared");
}

int main() {
    test_forward_list();
    return 0;
}
