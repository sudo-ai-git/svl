
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef uint64_t u64; typedef uint8_t u8;
#include "sha512fast.h"
static void hex(u8* b){for(int i=0;i<64;i++)printf("%02x",b[i]);printf("\n");}
int main(){
    init_tail();
    u8 msg[64]; for(int i=0;i<64;i++) msg[i]=i;
    u64 a[8],b[8];
    sha512_64(msg,a);      printf("fast64 : "); hex((u8*)a);
    sha512_generic(msg,64,b); printf("generic: "); hex((u8*)b);
    return 0;
}
