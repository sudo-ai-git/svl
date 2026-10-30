
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef uint64_t u64; typedef uint8_t u8;
#include "sha512fast.h"
static void hex(u8* b){for(int i=0;i<64;i++)printf("%02x",b[i]);printf("\n");}
int main(){
    init_tail();
    u64 a[8];
    sha512_generic((u8*)"abc",3,a); printf("abc    : "); hex((u8*)a);
    sha512_generic((u8*)"",0,a);    printf("empty  : "); hex((u8*)a);
    return 0;
}
