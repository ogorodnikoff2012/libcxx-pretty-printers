#include <string>

__attribute__((noinline)) void BREAK_HERE(const char *tag) {
    asm volatile("" :: "r"(tag));
}

void test_string() {
    std::string s;
    BREAK_HERE("empty");

    s = "hello";
    BREAK_HERE("short");

    s += ", world!";
    BREAK_HERE("short_append");

    // Exceed SSO buffer (typically 22 bytes on 64-bit libc++)
    s = "this string is long enough to exceed the small buffer optimization limit";
    BREAK_HERE("long");

    s = "back to short";
    BREAK_HERE("long_to_short");

    s.clear();
    BREAK_HERE("cleared");

    s = "special chars: \t\n\\\"";
    BREAK_HERE("special_chars");
}

int main() {
    test_string();
    return 0;
}
