// Fast oracle for Arweave Puzzle #10.
// Replicates the page's CryptoJS pipeline exactly (validated against PZL8 vector):
//   key_hex = SHA512 x11513(candidate) -> hex string (128 chars, used as ASCII password)
//   key[128], iv[16] = EVP_BytesToKey(MD5, 10000 iters, password=key_hex, salt)
//   AES-CBC decrypt, non-standard Nk=32 (1024-bit key), Nr=38 Rijndael
//   gate: plaintext contains "kty":"RSA"
// Fast path: only decrypt block 0 (gate lives there). Full decrypt only on hit.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <openssl/sha.h>
#include <openssl/md5.h>

typedef unsigned char u8;
typedef unsigned int u32;

static const u8 SBOX[256] = {
0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
};
static u8 INV_SBOX[256];
static const u8 RCON[15] = {0x00,0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1B,0x36,0x6C,0xD8,0xAB,0x4D};

static u32 sub_word(u32 w){ return ((u32)SBOX[(w>>24)&0xFF]<<24)|((u32)SBOX[(w>>16)&0xFF]<<16)|((u32)SBOX[(w>>8)&0xFF]<<8)|(u32)SBOX[w&0xFF]; }
static u32 rot_word(u32 w){ return ((w<<8)|(w>>24))&0xFFFFFFFF; }

// key expansion for Nk = key_bytes/4, Nr = Nk+6; returns malloc'd word array
static u32* key_expansion(const u8* key, int keylen, int* out_nr, int* out_total){
    int nk = keylen/4;
    int nr = nk + 6;
    int total = 4*(nr+1);
    u32* w = (u32*)malloc(total*sizeof(u32));
    for(int i=0;i<nk;i++) w[i] = ((u32)key[4*i]<<24)|((u32)key[4*i+1]<<16)|((u32)key[4*i+2]<<8)|(u32)key[4*i+3];
    for(int o=nk;o<total;o++){
        u32 s = w[o-1];
        if(o%nk==0){ s = sub_word(rot_word(s)) ^ ((u32)RCON[o/nk]<<24); }
        else if(nk>6 && o%nk==4){ s = sub_word(s); }
        w[o] = w[o-nk] ^ s;
    }
    *out_nr = nr; *out_total = total;
    return w;
}

static u8 gmul(u8 a, u8 b){ u8 p=0; for(int i=0;i<8;i++){ if(b&1) p^=a; u8 hi=a&0x80; a<<=1; if(hi) a^=0x1B; b>>=1; } return p; }

static void inv_shift_rows(u8* s){
    u8 o[16];
    for(int r=0;r<4;r++) for(int c=0;c<4;c++) o[r+4*c] = s[r+4*((c-r)&3)];
    memcpy(s,o,16);
}
static void inv_mix_columns(u8* s){
    u8 o[16];
    for(int c=0;c<4;c++){
        u8 s0=s[4*c],s1=s[4*c+1],s2=s[4*c+2],s3=s[4*c+3];
        o[4*c+0]=gmul(s0,14)^gmul(s1,11)^gmul(s2,13)^gmul(s3,9);
        o[4*c+1]=gmul(s0,9)^gmul(s1,14)^gmul(s2,11)^gmul(s3,13);
        o[4*c+2]=gmul(s0,13)^gmul(s1,9)^gmul(s2,14)^gmul(s3,11);
        o[4*c+3]=gmul(s0,11)^gmul(s1,13)^gmul(s2,9)^gmul(s3,14);
    }
    memcpy(s,o,16);
}
static void add_round_key(u8* s, const u32* w, int rnd){
    for(int c=0;c<4;c++){
        u32 wb = w[rnd*4+c];
        u8 b0=(wb>>24)&0xFF,b1=(wb>>16)&0xFF,b2=(wb>>8)&0xFF,b3=wb&0xFF;
        s[4*c+0]^=b0; s[4*c+1]^=b1; s[4*c+2]^=b2; s[4*c+3]^=b3;
    }
}
static void decrypt_block(const u8* ct, const u32* w, int nr, u8* out){
    u8 s[16]; memcpy(s,ct,16);
    add_round_key(s,w,nr);
    for(int rnd=nr-1;rnd>0;rnd--){
        inv_shift_rows(s);
        for(int i=0;i<16;i++) s[i]=INV_SBOX[s[i]];
        add_round_key(s,w,rnd);
        inv_mix_columns(s);
    }
    inv_shift_rows(s);
    for(int i=0;i<16;i++) s[i]=INV_SBOX[s[i]];
    add_round_key(s,w,0);
    memcpy(out,s,16);
}

// SHA512 chain x11513, return hex string (128 chars) into out[129]
static void sha512chain(const char* pw, char* out){
    u8 buf[64]; unsigned int len = (unsigned int)strlen(pw);
    SHA512((const u8*)pw, len, buf);
    for(int i=0;i<11512;i++){ u8 tmp[64]; SHA512(buf,64,tmp); memcpy(buf,tmp,64); }
    for(int i=0;i<64;i++) sprintf(out+2*i,"%02x",buf[i]);
    out[128]=0;
}

// EVP_BytesToKey: MD5, iterations, password = key_hex(128 ascii), salt 8 bytes -> keylen+ivlen bytes
static void evp_kdf(const char* pw, const u8* salt, int keylen, int ivlen, int iters, u8* out){
    int total = keylen+ivlen, got=0;
    u8 prev[16]; int prevlen=0;
    while(got<total){
        MD5_CTX c; MD5_Init(&c);
        if(prevlen) MD5_Update(&c,prev,prevlen);
        MD5_Update(&c,pw,strlen(pw));
        MD5_Update(&c,salt,8);
        u8 block[16]; MD5_Final(block,&c);
        for(int i=1;i<iters;i++){ MD5_CTX c2; MD5_Init(&c2); MD5_Update(&c2,block,16); MD5_Final(block,&c2); }
        int n = (total-got<16)?(total-got):16;
        memcpy(out+got,block,n); got+=n;
        memcpy(prev,block,16); prevlen=16;
    }
}

int main(int argc, char** argv){
    if(argc<3){ fprintf(stderr,"usage: %s <cipher_b64_file> <cands_file>\n",argv[0]); return 2; }
    for(int i=0;i<256;i++) INV_SBOX[SBOX[i]]=i;
    // read ciphertext b64
    FILE* f = fopen(argv[1],"rb"); if(!f){perror("ct");return 1;}
    fseek(f,0,SEEK_END); long clen=ftell(f); fseek(f,0,SEEK_SET);
    char* cb64 = malloc(clen+1); fread(cb64,1,clen,f); cb64[clen]=0; fclose(f);
    while(clen>0 && (cb64[clen-1]=='\n'||cb64[clen-1]=='\r'||cb64[clen-1]==' ')) cb64[--clen]=0;
    // base64 decode
    static int b64map[256]; for(int i=0;i<256;i++) b64map[i]=-1;
    const char* A="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    for(int i=0;i<64;i++) b64map[(u8)A[i]]=i;
    u8* raw = malloc(clen); int rl=0;
    { int val=0,bits=0; for(long i=0;i<clen;i++){ int d=b64map[(u8)cb64[i]]; if(d<0) continue; val=(val<<6)|d; bits+=6; if(bits>=8){ bits-=8; raw[rl++]=(u8)((val>>bits)&0xFF); } } }
    if(rl<16 || memcmp(raw,"Salted__",8)!=0){ fprintf(stderr,"bad ciphertext\n"); return 1; }
    u8 salt[8]; memcpy(salt,raw+8,8);
    const u8* body = raw+16; int blen = rl-16;
    // read candidates
    f = fopen(argv[2],"rb"); if(!f){perror("cands");return 1;}
    char* line=NULL; size_t cap=0; ssize_t n; int tested=0, hits=0;
    const char* GATE = "\"kty\":\"RSA\"";
    while((n=getline(&line,&cap,f))!=-1){
        while(n>0 && (line[n-1]=='\n'||line[n-1]=='\r')) line[--n]=0;
        if(n==0) continue;
        char keyhex[129]; sha512chain(line,keyhex);
        u8 derived[144]; evp_kdf(keyhex,salt,128,16,10000,derived);
        int nr,total; u32* w = key_expansion(derived,128,&nr,&total);
        // fast path: decrypt block 0 only
        u8 p0[16]; decrypt_block(body,w,nr,p0);
        u8 blk[16]; for(int i=0;i<16;i++) blk[i]=p0[i]^derived[128+i];
        tested++;
        // check gate in first block (need 10 bytes; block is 16)
        int hit=0;
        for(int i=0;i+10<=16;i++){ if(memcmp(blk+i,GATE,10)==0){ hit=1; break; } }
        if(hit){
            printf("MATCH: %s\n", line); fflush(stdout); hits++;
        }
        free(w);
    }
    printf("DONE tested=%d hits=%d\n",tested,hits);
    return 0;
}
