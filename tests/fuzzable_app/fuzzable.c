#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char* argv[])
{
    char buf[10];
    int len = read(0, buf, sizeof(buf));
    if (len < 5) {
        return 0;
    }
    if (buf[0] != 'F') return 2;
    if (buf[1] != 'U') return 3;
    if (buf[2] != 'Z') return 4;
    if (buf[3] != 'Z') return 5;
    if (buf[4] != '!') return 6;
    abort();
}
