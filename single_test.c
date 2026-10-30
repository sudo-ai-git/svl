
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef uint64_t u64; typedef uint8_t u8;
#include "sha512fast.h"
int main(){
    u64 st[8];
    sha512_generic((const u8*)"abc", 3, st);
    for(int i=0;i<8;i++) printf("%016llx", (unsigned long long)st[i]);
    printf("\\n");
    return 0;
}
