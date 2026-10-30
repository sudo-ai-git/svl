#!/usr/bin/env python3
"""PZL11 — alpha<255 connected components as a 32-byte key.

There are EXACTLY 32 alpha<255 components with size>=3 (the 'short lines
around the ship' the community noted). Test their size/width/height/length
as a 32-byte private key, across every natural ordering.
"""
from PIL import Image
import numpy as np
from scipy import ndimage
from coincurve import PublicKey
from Crypto.Hash import keccak

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140

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
        if a == PRIZE: print("  *** MATCH ***", name, bytes(b).hex()); hits.append(name)
        return a
    return None

arr = np.array(Image.open(IMG)); gray = arr[:, :, 0].astype(np.uint8); alpha = arr[:, :, 1].astype(np.uint8)
H, W = gray.shape
mask = (alpha < 255)
lbl, n = ndimage.label(mask)
comps = []
for c in range(1, n + 1):
    ys, xs = np.where(lbl == c)
    size = len(ys)
    if size < 3:
        continue
    length = int(round(np.hypot(xs.max()-xs.min(), ys.max()-ys.min())))
    cx = int(xs.mean()); cy = int(ys.mean())
    comps.append(dict(size=size, w=int(xs.max()-xs.min()+1), h=int(ys.max()-ys.min()+1),
                      length=length, cx=cx, cy=cy, x0=int(xs.min()), y0=int(ys.min())))
print(f"components size>=3: {len(comps)}")
for thresh_label, minsize in [("size>=3", 3), ("size>=2", 2), ("all", 1)]:
    cc = [c for c in comps if c['size'] >= minsize]
    if len(cc) != 32:
        continue
    # orderings
    orderings = {
        "label": list(range(len(cc))),
        "read": sorted(range(len(cc)), key=lambda i: (cc[i]['cy'], cc[i]['cx'])),
        "x": sorted(range(len(cc)), key=lambda i: cc[i]['cx']),
        "y": sorted(range(len(cc)), key=lambda i: cc[i]['cy']),
        "x0y0": sorted(range(len(cc)), key=lambda i: (cc[i]['x0'], cc[i]['y0'])),
        "size": sorted(range(len(cc)), key=lambda i: cc[i]['size']),
    }
    props = ["size", "w", "h", "length", "cx", "cy"]
    for oname, oidx in orderings.items():
        for p in props:
            vals = [cc[i][p] for i in oidx]
            if max(vals) < 256:
                chk(f"{thresh_label}-{oname}-{p}", bytes(int(v) & 0xFF for v in vals))
                # reversed
                chk(f"{thresh_label}-{oname}-{p}-rev", bytes(int(v) & 0xFF for v in vals[::-1]))
            # 2-byte packs
            b = b''.join(int(v).to_bytes(2, 'big') for v in vals)
            chk(f"{thresh_label}-{oname}-{p}-16be[:32]", b[:32])
            bl = b''.join(int(v).to_bytes(2, 'little') for v in vals)
            chk(f"{thresh_label}-{oname}-{p}-16le[:32]", bl[:32])
    # consecutive differences in reading order
    rv = [cc[i]['size'] for i in orderings['read']]
    diff = bytes(((rv[(k+1) % len(rv)] - rv[k]) & 0xFF) for k in range(len(rv)))
    chk("size-read-diff", diff)

print("alpha-components hits:", len(hits))
