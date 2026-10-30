#!/usr/bin/env python3
import numpy as np, hashlib, hmac, math
from PIL import Image
from eth_account import Account
arr = np.array(Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png'))
g = arr[:,:,0].astype(np.uint8); a = arr[:,:,1].astype(np.uint8)
PRIZE = 'ff2142e98e09b5344994f9beb9c56c95506b9f17'.lower()
# BIP39 English wordlist (2048 words)
import subprocess, os
WL = []
if os.path.exists('/home/sudosudo/bip39.txt'):
    WL = [w.strip() for w in open('/home/sudosudo/bip39.txt').read().splitlines() if w.strip()]
else:
    import urllib.request
    for line in urllib.request.urlopen('https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt', timeout=20).read().decode().splitlines():
        WL.append(line.strip())

def eval_key(label, b):
    if isinstance(b, np.ndarray): b = b.tobytes()
    if len(b) != 32: return
    for t, d in [('raw', b)]:
        ck = int.from_bytes(d, 'big')
        if not (0 < ck < 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140): continue
        try:
            addr = Account.from_key(d).address.lower()
        except Exception:
            continue
        if addr == PRIZE: print("HITCH", label, t, d.hex(), addr)

ys, xs = np.where(a < 255)
av = a[ys, xs].astype(np.uint8)
gv = g[ys, xs].astype(np.uint8)
print("sail:", len(av))

# E1: alpha 5-bit-as-symbol
bits = 0; n = 0; out = bytearray()
for v in av:
    v = int(v) - 224
    bits = (bits << 5) | v; n += 5
    while n >= 8:
        out.append((bits >> (n - 8)) & 0xFF); n -= 8
if n > 0: out.append((bits << (8 - n)) & 0xFF)
print("alpha5bits len", len(out), "first32:", out[:32].hex())
eval_key("alpha5_first32", out[:32])
eval_key("alpha5_last32", out[-32:])

# E2: sail gray as raw bytes
eval_key("sail_gray_raw", gv)
eval_key("sail_gray_last32", gv[-32:])

# E3: alpha/gray bytewise ops
a_xor_g = bytes([x ^ y for x, y in zip(av, gv)])
a_sum_g = bytes([(x + y) & 0xFF for x, y in zip(av, gv)])
for name, b in [("alpha_xor_gray", a_xor_g), ("alpha_plus_gray", a_sum_g)]:
    eval_key(name, b[:32]); eval_key(name, b[-32:])

# E4: photo-gate on alpha (cos2 model)
def cos2(x):
    return int((math.cos(x * math.pi / 2.0)) ** 2 * 255 + 0.5)
cos_out = bytes([cos2(v / 255.0) for v in av])
eval_key("photo_cos2_alpha", cos_out[:32])

# E7: sail alpha in DIFFERENT path orders -> keys
def order_alpha(order):
    idx = np.lexsort((xs, ys)) if order == "row-major" else \
          np.lexsort((ys, xs)) if order == "col-major" else \
          np.argsort(av) if order == "by_alpha" else \
          np.arange(len(av))
    return av[idx]
for ordname, idx in [("row-major", np.lexsort((xs, ys))),
                      ("col-major", np.lexsort((ys, xs))),
                      ("by_alpha", np.argsort(av))]:
    ab = av[idx]
    # 11-bit BIP39 word indices -> 12 words -> derive seed
    bits = 0; nbits = 0; widx = []
    for v in ab:
        v = int(v) - 224
        bits = (bits << 5) | v; nbits += 5
        while nbits >= 11:
            widx.append((bits >> (nbits - 11)) & 0x7FF)
            nbits -= 11
    if len(widx) >= 12:
        words = [WL[i & 0x7FF] for i in widx[:12]]
        k = hashlib.pbkdf2_hmac('sha512', ' '.join(words).encode(), b'', 2048)[:32]
        addr = Account.from_key(k).address.lower()
        if addr == PRIZE:
            print("HITCH", ordname, "alpha->11bit->words")
    # each ordering as first32/last32 raw bytes
    eval_key(ordname + "_first32", ab[:32])
    eval_key(ordname + "_last32", ab[-32:])
    # col-major 2-byte-per-pixel (alpha high-byte, gray low-byte)
    if ordname == "col-major":
        ab2 = b''.join(((int(av[i]) << 8) | int(gv[idx][i])).to_bytes(2, 'big') for i in range(len(idx)))
        eval_key(ordname + "_alpha2byte", ab2[:32])
        eval_key(ordname + "_alpha2byte_last32", ab2[-32:])
