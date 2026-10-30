#!/usr/bin/env python3
"""Contour-path experiment for the sail alpha<255 outline.

The open lead from PZL11_NOTES: "sailboat alpha-outline path (434 px) as an
ordered byte stream."

We trace the sail's connected silhouette as ONE path (contour-order), then
read the alpha and gray values along that path as candidate keys.
"""

import numpy as np
import hashlib
from PIL import Image
from eth_account import Account
import urllib.request

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = 'ff2142e98e09b5344994f9beb9c56c95506b9f17'.lower()
WL = []
for _line in urllib.request.urlopen('https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt', timeout=20).read().decode().splitlines():
    WL.append(_line.strip())



def eval_key(label, b):
    if isinstance(b, np.ndarray): b = b.tobytes()
    if len(b) != 32: return
    for t, d in [('raw', b)]:
        ck = int.from_bytes(d, 'big')
        if not (0 < ck < 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140):
            continue
        try:
            addr = Account.from_key(d).address.lower()
        except Exception:
            continue
        if addr == PRIZE:
            print("HITCH", label, t, d.hex(), addr)

arr = np.array(Image.open(IMG))
g = arr[:,:,0].astype(np.uint8); a = arr[:,:,1].astype(np.uint8)
H, W = a.shape

# 1) connected components of alpha<255
seen = np.zeros_like(a, bool)
comps = []
for i in range(H):
    for j in range(W):
        if a[i,j] < 255 and not seen[i,j]:
            stack = [(i,j)]; seen[i,j] = True; comp = []
            while stack:
                y,x = stack.pop(); comp.append((y,x))
                for dy in (-1,0,1):
                    for dx in (-1,0,1):
                        ny,nx = y+dy, x+dx
                        if 0<=ny<H and 0<=nx<W and not seen[ny,nx] and a[ny,nx]<255:
                            seen[ny,nx] = True; stack.append((ny,nx))
            comps.append(comp)
comp = max(comps, key=len)
print("sail px:", len(comp))
pts = set(comp)

# Start at top-leftmost; trace the outline by following connected cells
# in a CONTIGUOUS path (deep-first, consistent direction).
# We build the path by: start, then at each step move to an unvisited
# neighbor that keeps the path "connected" (contiguity), preferring a
# consistent turning direction (clockwise).
dirs = [(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1)]
start = min(comp, key=lambda p:(p[0], p[1]))
path = [start]
visited = {start}
cur = start
while len(path) < len(comp):
    y, x = cur
    nxt = None
    # try clockwise directions; pick the first unvisited neighbor
    for dy, dx in dirs:
        if (y+dy, x+dx) in pts and (y+dy, x+dx) not in visited:
            nxt = (y+dy, x+dx); break
    if nxt is None:
        # path stuck; try any unvisited neighbor (fallback)
        for dy, dx in dirs:
            nxt2 = (y+dy, x+dx)
            if nxt2 in pts and nxt2 not in visited:
                nxt = nxt2; break
    if nxt is None:
        break
    cur = nxt
    path.append(cur)
    visited.add(cur)

print("path traced:", len(path), "of", len(pts))

# alpha and gray along the path
apath = a[ np.array([p[0] for p in path]), np.array([p[1] for p in path]) ].astype(np.uint8)
gpath = g[ np.array([p[0] for p in path]), np.array([p[1] for p in path]) ].astype(np.uint8)

# E1: alpha along path -> raw 32-byte key(s)
eval_key("path_alpha_first32", apath[:32])
eval_key("path_alpha_last32", apath[-32:])

# E2: path_alpha as 5-bit-per-symbol -> key
bits = 0; n = 0; out = bytearray()
for v in apath:
    v = int(v) - 224
    bits = (bits << 5) | v; n += 5
    while n >= 8:
        out.append((bits >> (n - 8)) & 0xFF); n -= 8
if n > 0: out.append((bits << (8 - n)) & 0xFF)
eval_key("path_alpha5_first32", out[:32])
eval_key("path_alpha5_last32", out[-32:])

# E3: path_alpha XOR path_gray, path_alpha+path_gray
eval_key("path_alpha_xor_gray", apath ^ gpath)
eval_key("path_alpha_plus_gray", (apath + gpath) & 0xFF)

# E4: path_alpha and path_gray as 2-byte pairs
ab2 = b''.join(((int(av) << 8) | int(gv)).to_bytes(2, 'big') for av, gv in zip(apath, gpath))
eval_key("path_alpha2byte_first32", ab2[:32])
eval_key("path_alpha2byte_last32", ab2[-32:])

# E5: 11-bit BIP39 word indices from path alpha -> 12 words -> seed
bits = 0; n = 0; widx = []
for v in apath:
    v = int(v) - 224
    bits = (bits << 5) | v; n += 5
    while n >= 11:
        widx.append((bits >> (n - 11)) & 0x7FF)
        n -= 11
if len(widx) >= 12:
    words = [WL[i & 0x7FF] for i in widx[:12]]
    k = hashlib.pbkdf2_hmac('sha512', ' '.join(words).encode(), b'', 2048)[:32]
    addr = Account.from_key(k).address.lower()
    if addr == PRIZE:
        print("HITCH path words:", ' '.join(words))

print("DONE")
