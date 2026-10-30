// Optimized SHA512 x11513 chain for PZL10.
// For iterations >= 2 the input is always the 64-byte digest, so the second
// padded block (0x80 at offset 64, length 512 bits) is CONSTANT and its message
// schedule is precomputed once. Each iteration then = 1 variable compression
// (block 0, 64 bytes) + 1 constant compression.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

typedef uint64_t u64;
typedef uint8_t u8;

static const u64 K[80] = {
0x428a2f98d728ae22ULL,0x7137449123ef65cdULL,0xb5c0fbcfec4d3b2fULL,0xe9b5dba58189dbbcULL,
0x3956c25bf348b538ULL,0x59f111f1b605d019ULL,0x923f82a4af194f9bULL,0xab1c5ed5da6d8118ULL,
0xd807aa98a3030242ULL,0x12835b0145706fbeULL,0x243185be4ee4b28cULL,0x550c7dc3d5ffb4e2ULL,
0x72be5d74f27b896fULL,0x80deb1fe3b1696b1ULL,0x9bdc06a725c71235ULL,0xc19bf174cf692694ULL,
0xe49b69c19ef14ad2ULL,0xefbe4786384f25e3ULL,0x0fc19dc68b8cd5b5ULL,0x240ca1cc77ac9c65ULL,
0x2de92c6f592b0275ULL,0x4a7484aa6ea6e483ULL,0x5cb0a9dcbd41fbd4ULL,0x76f988da831153b5ULL,
0x983e5152ee66dfabULL,0xa831c66d2db43210ULL,0xb00327c898fb213fULL,0xbf597fc7beef0ee4ULL,
0xc6e00bf33da88fc2ULL,0xd5a79147930aa725ULL,0x06ca6351e003826fULL,0x142929670a0e6e70ULL,
0x27b70a8546d22ffcULL,0x2e1b21385c26c926ULL,0x4d2c6dfc5ac42aedULL,0x53380d139d95b3dfULL,
0x650a73548baf63deULL,0x766a0abb3c77b2a8ULL,0x81c2c92e47edaee6ULL,0x92722c851482353bULL,
0xa2bfe8a14cf10364ULL,0xa81a664bbc423001ULL,0xc24b8b70d0f89791ULL,0xc76c51a30654be30ULL,
0xd192e819d6ef5218ULL,0xd69906245565a910ULL,0xf40e35855771202aULL,0x106aa07032bbd1b8ULL,
0x19a4c116b8d2d0c8ULL,0x1e376c085141ab53ULL,0x2748774cdf8eeb99ULL,0x34b0bcb5e19b48a8ULL,
0x391c0cb3c5c95a63ULL,0x4ed8aa4ae3418acbULL,0x5b9cca4f7763e373ULL,0x682e6ff3d6b2b8a3ULL,
0x748f82ee5defb2fcULL,0x78a5636f43172f60ULL,0x84c87814a1f0ab72ULL,0x8cc702081a6439ecULL,
0x90befffa23631e28ULL,0xa4506cebde82bde9ULL,0xbef9a3f7b2c67915ULL,0xc67178f2e372532bULL,
0xca273eceea26619cULL,0xd186b8c721c0c207ULL,0xeada7dd6cde0eb1eULL,0xf57d4f7fee6ed178ULL,
0x06f067aa72176fbaULL,0x0a637dc5a2c898a6ULL,0x113f9804bef90daeULL,0x1b710b35131c471bULL,
0x28db77f523047d84ULL,0x32caab7b40c72493ULL,0x3c9ebe0a15c9bebcULL,0x431d67c49c100d4cULL,
0x4cc5d4becb3e42b6ULL,0x597f299cfc657e2aULL,0x5fcb6fab3ad6faecULL,0x6c44198c4a475817ULL,
};
static const u64 IV[8] = {0x6a09e667f3bcc908ULL,0xbb67ae8584caa73bULL,0x3c6ef372fe94f82bULL,
0xa54ff53a5f1d36f1ULL,0x510e527fade682d1ULL,0x9b05688c2b3e6c1fULL,0x1f83d9abfb41bd6bULL,
0x5be0cd19137e2179ULL};

static inline u64 rotr(u64 x,int n){ return (x>>n)|(x<<(64-n)); }

static inline void compress(u64* st, const u64* w){
    u64 a=st[0],b=st[1],c=st[2],d=st[3],e=st[4],f=st[5],g=st[6],h=st[7];
    for(int i=0;i<80;i++){
        u64 S1 = rotr(e,14)^rotr(e,18)^rotr(e,41);
        u64 ch = (e&f)^(~e&g);
        u64 t1 = h + S1 + ch + K[i] + w[i];
        u64 S0 = rotr(a,28)^rotr(a,34)^rotr(a,39);
        u64 mj = (a&b)^(a&c)^(b&c);
        u64 t2 = S0 + mj;
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    st[0]+=a; st[1]+=b; st[2]+=c; st[3]+=d; st[4]+=e; st[5]+=f; st[6]+=g; st[7]+=h;
}

// expand message schedule for a 128-byte block
static inline void sched(const u8* blk, u64* w){
    for(int i=0;i<16;i++){
        w[i]=((u64)blk[8*i]<<56)|((u64)blk[8*i+1]<<48)|((u64)blk[8*i+2]<<40)|((u64)blk[8*i+3]<<32)
            |((u64)blk[8*i+4]<<24)|((u64)blk[8*i+5]<<16)|((u64)blk[8*i+6]<<8)|((u64)blk[8*i+7]);
    }
    for(int i=16;i<80;i++){
        u64 s0 = rotr(w[i-15],1)^rotr(w[i-15],8)^(w[i-15]>>7);
        u64 s1 = rotr(w[i-2],19)^rotr(w[i-2],61)^(w[i-2]>>6);
        w[i]=w[i-16]+s0+w[i-7]+s1;
    }
}

// SHA512 of a 64-byte message = TWO compression blocks:
//   Block 1: bytes 0..63 = message, byte 64 = 0x80, bytes 65..127 = 0
//   Block 2: bytes 0..119 = 0, bytes 120..127 = 512-bit length
// The second block is fully constant. We precompute its compression contribution.
static u64 ST2[8];               // post-compression state delta of constant block 2
static int TAIL_INIT = 0;
static void init_tail(void){
    if(TAIL_INIT) return; TAIL_INIT=1;
    // Block 2: all zeros except length at bytes 120..127
    u8 blk2[128]; memset(blk2,0,128);
    blk2[126]=0x02; blk2[127]=0x00;  // 512 bits = 0x0200
    u64 w2[80]; sched(blk2, w2);
    u64 st2[8]; memcpy(st2,IV,sizeof(IV));
    compress(st2, w2);
    memcpy(ST2, st2, sizeof(ST2));
}

static inline void sha512_64(const u8* msg64, u64* out){
    // Block 1: 64-byte message + 0x80 at byte 64 + zeros
    u8 blk1[128]; memset(blk1,0,128);
    memcpy(blk1, msg64, 64);
    blk1[64] = 0x80;
    u64 w1[80]; sched(blk1, w1);
    u64 st[8]; memcpy(st,IV,sizeof(IV));
    compress(st, w1);
    // Block 2: constant (precomputed)
    for(int i=0;i<8;i++) st[i] += ST2[i];
    memcpy(out, st, 64);
}

// generic SHA512 for the FIRST hash (variable-length password)
static void sha512_generic(const u8* data, size_t len, u64* out){
    u64 st[8]; memcpy(st,IV,sizeof(IV));
    size_t total = len + 1 + 16;               // +0x80 + 128-bit length
    size_t padded = ((total + 127)/128)*128;
    u8* buf = (u8*)calloc(padded,1);
    memcpy(buf,data,len); buf[len]=0x80;
    u64 bits = (u64)len*8;
    for(int i=0;i<8;i++) buf[padded-1-i] = (u8)((bits>>(8*i))&0xFF);
    for(size_t off=0; off<padded; off+=128){ u64 w[80]; sched(buf+off,w); compress(st,w); }
    free(buf);
    memcpy(out,st,64);
}

// chain: H0 = sha512(pw); H_{n} = sha512_64(H_{n-1}); 11512 times. Output hex of final.
void sha512chain(const char* pw, char* hexout){
    init_tail();
    u64 st[8]; sha512_generic((const u8*)pw, strlen(pw), st);
    for(int i=0;i<11512;i++) sha512_64((const u8*)st, st);
    u8* b=(u8*)st;
    for(int i=0;i<64;i++) sprintf(hexout+2*i,"%02x",b[i]);
    hexout[128]=0;
}

#ifdef CHAIN_MAIN
int main(int argc,char**argv){
    char out[129];
    sha512chain(argv[1], out);
    printf("%s\n", out);
    return 0;
}
#endif
