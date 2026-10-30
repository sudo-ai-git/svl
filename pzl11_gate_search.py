#!/usr/bin/env python3
import numpy as np, hashlib, math
from PIL import Image
from eth_account import Account
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
arr = np.array(Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png'))
g = arr[:,:,0].astype(np.uint8); a = arr[:,:,1].astype(np.uint8)
ys, xs = np.where(a < 255)
av = a[ys, xs].astype(np.float64); gv = g[ys, xs].astype(np.float64)

# candidate gate-param vectors derived from the 12 heights
thetas = [(167, 245, 144, 212), (167, 245, 144, 0), (167, 245, 144, 1)]
for (tA, tB, p0, inv) in thetas:
    I = np.cos((p0 + tA*av + tB*gv)/2 * np.pi/180)  # degrees -> radians
    img = (I >= 0.5).astype(np.uint8)
    # invert bit
    img = np.bitwise_xor(img, inv & 1)
    k = hashlib.sha256(img.astype(np.uint8)).digest()
    if k == PRIZE:
        print("HITCH gate params", (tA, tB, p0, inv))
print("gate-grid done")
