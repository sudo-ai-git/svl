#!/usr/bin/env python3
"""PZL11 creative-signal solver (applies the signal-discrimination methodology).

The creative-gate methodology classifies a signal as 'creative' (novel,
high-entropy, above threshold) vs 'repetitive' (low-entropy, below threshold).
The threshold is the oracle: an ETH address that derives to the prize
0xff2142e98e09b5344994f9beb9c56c95506b9f17.

The image's 'creative' channels are the sailboat alpha outline (434 px,
non-repetitive structure), the row-0 watermark curve (147 values), and the
skyline profile. These are where the alternative-form (BIP39/seed) encoding
should reside -- not in the repetitive full-bitplanes or pure grayscale.

Applies the oracle gate to candidate encodings from each creative channel.
"""

import sys
import math
import hashlib
import numpy as np
from PIL import Image
from coincurve import PublicKey
from eth_account import Account

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
BASE = '/home/sudosudo/.hermes/cache/scratch/pzl11'

class Oracle:
    def __init__(self):
        self.n = 0
        self.hits = []
    def check(self, pk, name):
        self.n += 1
        if isinstance(pk, int):
            pk = pk.to_bytes(32, 'big')
        pk = bytes(pk)[-32:].rjust(32, b'\x00')
        try:
            a = Account.from_key(pk).address.lower()
        except Exception:
            return False
        if a == PRIZE.lower():
            self.hits.append((name, pk.hex()))
            print("!!!! HIT", name, pk.hex(), a)
            return True
        return False
    def try_bytes(self, b, name):
        if isinstance(b, (np.ndarray,)):
            b = b.tobytes()
        if not b:
            return
        self.check(b, name + ":first32")
        self.check(b[-32:], name + ":last32")
        for hn, hf in (("sha256", hashlib.sha256),
                       ("sha3", hashlib.sha3_256),
                       ("md5", hashlib.md5),
                       ("sha512", hashlib.sha512)):
            r = hf(b); d = r if isinstance(r, bytes) else r.digest()
            self.check(d, name + ":" + hn)
            self.check(d[::-1], name + ":" + hn + "rev")
        if len(b) >= 64:
            for sl, tt in ((b[:64], "hex_first"), (b[-64:], "hex_last")):
                try:
                    self.check(bytes.fromhex(sl.decode("ascii")), name + ":" + tt)
                except Exception:
                    pass

def oracle_self_test():
    assert Account.from_key((1).to_bytes(32, 'big')).address.lower() == \
        "0x7e5f4552091a69125d5dfcb7b8c2659029395bdf", "oracle self-test failed"

def sail_outline(alpha, gray):
    ys, xs = np.where(alpha < 255)
    idx = np.lexsort((xs, ys))
    return alpha[ys[idx], xs[idx]].astype(np.uint8), gray[ys[idx], xs[idx]].astype(np.uint8)

def row0_watermark(gray):
    r0 = gray[0]
    nz = np.where(r0 != 255)[0]
    return gray[0, nz].astype(np.uint8), nz

def building_profile(gray):
    B = [(234,322,161,328),(326,412,78,323),(416,500,183,327),(502,676,107,319),
         (678,782,20,312),(884,978,201,307),(980,1140,72,322),(1142,1258,101,321),
         (1260,1348,176,313),(1350,1452,105,313),(1454,1510,163,307),(1514,1592,74,300)]
    H = [b[3]-b[2] for b in B]
    WID = [b[1]-b[0] for b in B]
    return H, WID

def load():
    arr = np.array(Image.open(IMG))
    gray = arr[:,:,0].astype(np.uint8)
    alpha = arr[:,:,1].astype(np.uint8)
    return gray, alpha

def run():
    o = Oracle()
    print("=== PZL11 creative-signal solver ===")
    print("oracle self-test:", "OK" if Account.from_key((1).to_bytes(32,'big')).address.lower()=="0x7e5f4552091a69125d5dfcb7b8c2659029395bdf" else "FAIL")
    gray, alpha = load()

    def try_bytes(b, name):
        o.try_bytes(b, name)

    # channel 1: sail outline (434 px)
    av, gv = sail_outline(alpha, gray)
    print("alpha<255 sail px:", len(av), "alpha vals:", sorted(set(av)))
    o.try_bytes(av, "sailOutline_alpha_raster")
    o.try_bytes(gv, "sailOutline_gray_raster")
    pairs = bytearray()
    for a, g in zip(av, gv):
        pairs.append(a & 0xFF); pairs.append(g & 0xFF)
    o.try_bytes(bytes(pairs), "sailOutline_alpha_gray_pair_16")
    pairs16le = bytearray()
    for a, g in zip(av, gv):
        pairs16le.append(a & 0xFF); pairs16le.append(g & 0xFF)
    o.try_bytes(bytes(pairs16le), "sailOutline_alpha_gray_pair_le")

    # channel 2: row-0 watermark (147 px)
    r0v, r0c = row0_watermark(gray)
    print("row0 watermark count:", len(r0v), "cols", r0c.min(), r0c.max())
    o.try_bytes(r0v, "row0_watermark_vals")
    o.try_bytes((255 - r0v) & 0xFF, "row0_watermark_255minus")
    o.try_bytes(r0c, "row0_watermark_cols")
    bits = []
    for v in r0v:
        for bit in range(5):
            bits.append((v >> bit) & 1)
    o.try_bytes(bytes(bits), "row0_watermark_bits")
    idxs = np.linspace(0, len(r0v)-1, 32).astype(int)
    o.try_bytes(r0v[idxs], "row0_watermark_smoothed_32")

    # channel 3: skyline profile
    H, WID = building_profile(gray)
    print("building heights:", H, "widths:", WID)
    o.try_bytes(b''.join(x.to_bytes(2,'big') for x in H+WID), "skyline_H_plus_WID_bytes")
    hi = b''.join(x.to_bytes(2,'big') for x in H)
    wi = b''.join(x.to_bytes(2,'big') for x in WID)
    o.try_bytes(hi + wi, "skyline_H_WID_2byteBE")

    # channel 4: gray values at alpha<255 positions
    o.try_bytes(gv, "sail_gray_raster_first32")
    o.try_bytes(gv[:32], "sail_gray_first32")
    o.try_bytes(gv[-32:], "sail_gray_last32")

    print(f"\ncandidates tested: {o.n}")
    print("hits:", len(o.hits))
    for name, pk in o.hits:
        print(" !!! HIT", name, pk)

if __name__ == '__main__':
    run()