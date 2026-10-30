#!/usr/bin/env python3
"""PZL11 — image-statistics campaign (fresh, untested hypotheses).

Integrated row/col intensity, gray values along the sailboat contour, gray
histogram, darkest-pixel sequences, per-column dark-area. Each -> 32-byte key.
"""
from PIL import Image
import numpy as np
from scipy import ndimage
from coincurve import PublicKey
from Crypto.Hash import keccak

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
arr = np.array(Image.open(IMG)); gray = arr[:, :, 0].astype(np.uint8); alpha = arr[:, :, 1].astype(np.uint8)
H, W = gray.shape
hits = []

def kc(b):
    h = keccak.new(digest_bits=256); h.update(b); return h.digest()
def der(p):
    if len(p) != 32: return None
    n = int.from_bytes(p, 'big')
    if n == 0 or n >= ORDER: return None
    try: return kc(PublicKey.from_secret(p).format(compressed=False)[1:])[12:]
    except Exception: return None
def chk(name, b):
    if isinstance(b, (bytes, bytearray)) and len(b) == 32:
        a = der(bytes(b))
        if a == PRIZE: print("  *** MATCH ***", name); hits.append(name)
        return a
def windows(name, seq):
    seq = bytes(seq)
    for s in range(len(seq)-31):
        chk(f"{name}[w{s}]", seq[s:s+32])

# 1. integrated intensity row/col sums -> mod 256
rowsum = (gray.astype(int).sum(axis=1) % 256).astype(np.uint8)
colsum = (gray.astype(int).sum(axis=0) % 256).astype(np.uint8)
chk("rowsum:first", rowsum[:32]); chk("rowsum:last", rowsum[-32:]); windows("rowsum", rowsum)
chk("colsum:first", colsum[:32]); chk("colsum:last", colsum[-32:]); windows("colsum", colsum)
# 2. dark-area per column (count of gray<128)
area = ((gray < 128).sum(axis=0)).astype(np.uint8)
chk("columndarkarea:first", area[:32]); windows("columndarkarea", area)
# 3. gray histogram (counts of each value 0..255) -> bytes
hist = np.bincount(gray.ravel(), minlength=256).astype(np.uint8)
chk("hist[:32]", hist[:32]); chk("hist[-32:]", hist[-32:])
hist255 = np.bincount(gray.ravel(), minlength=256)[1:]  # skip 0
chk("hist1[:32]", hist255[:32].astype(np.uint8))
# 4. darkest pixels: sort all pixels by value, take 32 lowest gray values
flat = gray.ravel()
lowest = np.sort(flat)[:32]
chk("lowest32:val", lowest.astype(np.uint8))
# positions of the 32 darkest pixels (x, then y)
order = np.argsort(flat)[:64]
ysx = np.unravel_index(order, gray.shape)
xs_d = ysx[1][:32]; ys_d = ysx[0][:32]
chk("darkest:x", (xs_d % 256).astype(np.uint8))
chk("darkest:y", (ys_d % 256).astype(np.uint8))
# 5. gray values ALONG the alpha<255 contour, in reading order
mask = (alpha < 255)
ys, xs = np.where(mask)
idx = np.lexsort((xs, ys))  # row-major
contour_gray = gray[ys[idx]]
contour_alpha = alpha[ys[idx]]
windows("contour_gray", contour_gray.astype(np.uint8))
windows("contour_255minus", (255 - contour_alpha).astype(np.uint8))
# 6. the sailboat contour length sequence (run-lengths of the contour)
print("contour pixels:", len(idx), "gray[:32]:", contour_gray[:32].tolist())
print("image-stats hits:", len(hits))
