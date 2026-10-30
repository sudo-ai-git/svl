
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef uint64_t u64; typedef uint8_t u8;
#include "sha512fast.h"
int main(){
    init_tail();
    u64 st[8];
    sha512_generic((const u8*)"testpw", 6, st);
    printf("iter0: "); for(int i=0;i<8;i++) printf("%016llx", (unsigned long long)st[i]); printf("\\n");
    sha512_64((const u8*)st, st);
    printf("iter1: "); for(int i=0;i<8;i++) printf("%016llx", (unsigned long long)st[i]); printf("\\n");
    return 0;
}
