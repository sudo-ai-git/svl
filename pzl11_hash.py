#!/usr/bin/env python3
"""PZL11 — image-hash / region hypotheses + render the sailboat region.

Test whether the private key = hash of the whole image or a salient region
(boat, skyline). Also render the left 'boat' region so letter-like strokes
(the community's 'text on the sail') are visible.
"""
from PIL import Image
import numpy as np, hashlib
from coincurve import PublicKey
from Crypto.Hash import keccak

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
arr = np.array(Image.open(IMG)); gray = arr[:, :, 0].astype(np.uint8); alpha = arr[:, :, 1].astype(np.uint8)
H, W = gray.shape

def kc(b):
    h = keccak.new(digest_bits=256); h.update(b); return h.digest()
def der(p):
    if len(p) != 32: return None
    n = int.from_bytes(p, 'big')
    if n == 0 or n >= ORDER: return None
    try: return kc(PublicKey.from_secret(p).format(compressed=False)[1:])[12:]
    except Exception: return None
hits = []
def chk(name, b):
    if isinstance(b, (bytes, bytearray)) and len(b) == 32:
        a = der(bytes(b))
        if a == PRIZE: print("  *** MATCH ***", name); hits.append(name)
        return a
    return None

raw = open(IMG, 'rb').read()
# whole-image hashes -> 32 bytes, and their windows won't apply (only 32/64)
for name, b in [("keccak(png)", kc(raw)), ("sha256(png)", hashlib.sha256(raw).digest()),
                ("keccak(gray)", kc(gray.tobytes())), ("sha256(gray)", hashlib.sha256(gray.tobytes()).digest()),
                ("keccak(alpha)", kc(alpha.tobytes())), ("sha256(alpha)", hashlib.sha256(alpha.tobytes()).digest())]:
    chk(name, b); chk(name+"[32:]", b[32:])

# region hashes: boat (left), skyline (center-right)
def region_hashes(r0, r1, c0, c1, tag):
    reg = gray[r0:r1, c0:c1]
    al = alpha[r0:r1, c0:c1]
    for nm, d in [("g", reg.tobytes()), ("a", al.tobytes()), ("ga", (reg.astype(int)*256+al).tobytes())]:
        chk(f"{tag}-{nm}:kc", kc(d)); chk(f"{tag}-{nm}:sha", hashlib.sha256(d).digest())
region_hashes(0, H, 0, 560, "boat")
region_hashes(0, H, 560, W, "skyline")
region_hashes(378, 1102, 0, 560, "boatbbox")

# --- render the boat region (left), strokes gray<180 ---
print("\n=== boat region x0-559, strokes gray<180, 1char~8x8 ===")
sub = (gray < 180) & (np.arange(W).reshape(1,-1) < 560)
for rb in range(0, H, 8):
    line = []
    for cb in range(0, 560, 8):
        blk = sub[rb:rb+8, cb:cb+8]
        line.append('#' if blk.any() else '.')
    print(''.join(line))
print("boat campaign hits:", len(hits))
