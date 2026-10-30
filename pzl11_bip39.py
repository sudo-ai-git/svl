#!/usr/bin/env python3
"""BIP39/seed-phrase derivation for PZL11.

The creative-gate oracle is the ETH-address discriminator. We need the 32-byte
key. The notes hint it is an alternative form: a BIP39 seed phrase -> PBKDF2
seed -> key. This probes the alpha/gray raster streams as entropy sources and
derives the 12-word (128-bit) BIP39 mnemonic, PBKDF2-hashes it to 64 bytes,
and gates each candidate through the oracle (address must equal
0xff2142e98e09b5344994f9beb9c56c95506b9f17).
"""

import numpy as np, hashlib
from PIL import Image
from eth_account import Account, Account as A

PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
WL = [w.strip() for w in open('/home/sudosudo/bip39.txt').read().splitlines() if w.strip()]
assert len(WL) == 2048, len(WL)

def sha256(b): return hashlib.sha256(b).digest()
def pbkdf2(key, salt, iterations=2048, dklen=64):
    return hashlib.pbkdf2_hmac('sha512', key, salt, iterations, dklen)

def bits_to_words(bits_str, wordlist):
    words=[]
    for i in range(12):
        idx=int(bits_str[i*11:(i+1)*11],2)
        words.append(wordlist[idx])
    return words

def mnemonic_from_bytes(ent_bits, wordlist, strength_bits=128):
    """ent_bits: 16 bytes entropy -> 128-bit mnemonic (12 words)."""
    if len(ent_bits)!=16: return None
    cs_bits = 4  # 128/4
    checksum_byte = sha256(ent_bits)[0] >> (8 - cs_bits)
    data = bytearray(ent_bits) + bytearray([checksum_byte])
    bits = bin(int.from_bytes(data,'big'))[2:].zfill(strength_bits+cs_bits)
    return bits_to_words(bits, wordlist)

def derive_key(mnemonic, passphrase=''):
    return pbkdf2(mnemonic.encode(), passphrase.encode(), 2048, 64)[:32]

def run():
    import sys
    sys.path.insert(0, '.openclaw/workspace')
    arr = np.array(Image.open('.openclaw/workspace/pzl11.png'))
    g = arr[:,:,0].astype(np.uint8); a = arr[:,:,1].astype(np.uint8)
    ys,xs = np.where(a<255)
    order = np.lexsort((xs, ys))
    av = a[ys[order], xs[order]].astype(np.uint8)
    gv = g[ys[order], xs[order]].astype(np.uint8)

    for label, ent_src in [("alpha",av),("gray",gv)]:
        for e16 in [ent_src[:16]]:
            for mwords in [mnemonic_from_bytes(e16,WL)]:
                if mwords:
                    seed = derive_key(' '.join(mwords))
                    addr = Account.from_key(seed).address.lower()
                    if addr==PRIZE.lower():
                        print("HITCH12",label,mwords,seed.hex(),addr)
                    # also try key = seed (64-byte hex) -> first32? No, seed IS 32 bytes
        # entropy 132 bits (128+4) directly
        data = ent_src[:17]
        val = int.from_bytes(data,'big')
        bits2 = bin(val)[2:].zfill(136)
        mwords2 = bits_to_words(bits2, WL)
        if mwords2:
            seed2 = derive_key(' '.join(mwords2))
            addr = Account.from_key(seed2).address.lower()
            if addr==PRIZE.lower():
                print("HITCH132",label,mwords2,seed2.hex(),addr)

if __name__=='__main__':
    run()