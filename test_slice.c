#include <stdio.h>
#include <string.h>
#include <openssl/sha.h>

int main(int argc, char** argv) {
    if(argc < 2) return 1;
    unsigned char hash[SHA512_DIGEST_LENGTH];
    const char* pw = argv[1];
    SHA512((const unsigned char*)pw, strlen(pw), hash);
    for(int i=0;i<11512;i++) SHA512(hash, SHA512_DIGEST_LENGTH, hash);
    char hex[129];
    for(int i=0;i<64;i++) sprintf(hex+i*2, "%02x", hash[i]);
    hex[128]=0;
    printf("full: %s\n", hex);
    printf("[0:20]: %.20s\n", hex);
    return 0;
}
