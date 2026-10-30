
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef uint64_t u64; typedef uint8_t u8;
#include "sha512fast.h"
int main(){
    init_W2();
    // Verify: sha512 of 64-byte input vs openssl
    u8 msg[64]; for(int i=0;i<64;i++) msg[i]=i;
    u64 st[8]; sha512_64(msg, st);
    u8* b=(u8*)st; for(int i=0;i<64;i++) printf("%02x",b[i]); printf("\n");
    return 0;
}
