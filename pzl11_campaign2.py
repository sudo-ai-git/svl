#!/usr/bin/env python3
"""PZL11 campaign v2 — subtle-band 2D watermark + skyline-profile exhaust.

- Render gray in [200,254] (excl 255): catches subtle near-white watermarks
  beyond the row-0 strip.
- Skyline top-edge profile: quantize to 1 byte/col, raw/neg/diff, all windows.
- Building segmentation (bottom-up baseline): heights/widths/positions.
Each 32-byte candidate -> ETH address -> compare to prize.
"""
from PIL import Image
import numpy as np
from coincurve import PublicKey
from Crypto.Hash import keccak

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140

def keccak256(b):
    h = keccak.new(digest_bits=256); h.update(b); return h.digest()

def der(p):
    if len(p) != 32:
        return None
    n = int.from_bytes(p, 'big')
    if n == 0 or n >= ORDER:
        return None
    try:
        return keccak256(PublicKey.from_secret(p).format(compressed=False)[1:])[12:]
    except Exception:
        return None

assert der((1).to_bytes(32, 'big')).hex() == '7e5f4552091a69125d5dfcb7b8c2659029395bdf'

arr = np.array(Image.open(IMG))
gray = arr[:, :, 0].astype(np.uint8); H, W = gray.shape
hits = []

def chk(name, b):
    if isinstance(b, np.ndarray):
        b = b.tobytes()
    if isinstance(b, (bytes, bytearray)) and len(b) == 32:
        a = der(bytes(b))
        if a == PRIZE:
            print("  *** MATCH ***", name); hits.append(name)

# ---- subtle band render ----
subtle = (gray >= 190) & (gray <= 254)
print("=== subtle near-white band [190,254] (count=%d) ===" % int(subtle.sum()))
VH, VW = H // 8 + 1, W // 12
for rb in range(VH):
    line = []
    for cb in range(VW):
        blk = subtle[rb*8:(rb+1)*8, cb*12:(cb+1)*12]
        line.append('#' if blk.any() else '.')
    print(''.join(line))

# ---- skyline top-edge profile ----
top = np.full(W, H, dtype=np.int64)
for c in range(W):
    r = np.nonzero(gray[:, c] < 128)[0]
    if len(r):
        top[c] = r[0]
# quantize to 1 byte
prof8 = np.clip((top.astype(int) * 255 // H), 0, 255).astype(np.uint8)
chk("profile8:first32", prof8[:32]); chk("profile8:last32", prof8[-32:])
neg = (255 - prof8).astype(np.uint8)
chk("profile8-neg:first32", neg[:32])
# differences
diff = np.diff(prof8.astype(int)).astype(np.int8)
chk("profile-diff:first32", diff[:32].tobytes())
# all windows
for s in range(W - 31):
    chk(f"profile8[w{s}]", prof8[s:s+32])
for s in range(W - 32):
    chk(f"profile8-neg[w{s}]", neg[s:s+32])

# ---- building segmentation (bottom-up baseline) ----
# baseline = shallowest row that is dark across >95% of width, scanning from bottom
darkfrac = (gray < 128).mean(axis=1)
base = H - 1 - int(np.flipud(darkfrac > 0.9).argmax()) if (darkfrac > 0.9).any() else H - 1
present = top < (base - 20)
runs = []; i = 0
while i < W:
    if present[i]:
        j = i
        while j < W and present[j]:
            j += 1
        runs.append((i, j - 1)); i = j
    else:
        i += 1
heights = [base - int(top[i:j+1].max()) for (i, j) in runs]
widths = [j - i + 1 for (i, j) in runs]
print(f"\nbaseline={base} buildings={len(runs)} heights={heights} widths={widths}")
def seqs(names, seq):
    seq = bytes(np.asarray(seq, dtype=np.uint8).tolist()) if isinstance(seq, list) and seq and seq[0] < 256 else None
    if seq:
        chk(f"{names}:first32", seq[:32]); chk(f"{names}:last32", seq[-32:])
        for s in range(len(seq)-31):
            chk(f"{names}[w{s}]", seq[s:s+32])
h8 = np.array(heights, dtype=np.uint8).tobytes()
chk("heights8:first32", h8[:32])
for s in range(len(h8)-31):
    chk(f"heights8[w{s}]", h8[s:s+32])
h16b = b''.join(x.to_bytes(2, 'big') for x in heights)
h16l = b''.join(x.to_bytes(2, 'little') for x in heights)
for b in (h16b, h16l):
    chk("h16:first32", b[:32])
    for s in range(len(b)-31):
        chk("h16[w]", b[s:s+32])
w8 = np.array(widths, dtype=np.uint8).tobytes()
chk("widths8:first32", w8[:32])
for s in range(len(w8)-31):
    chk(f"widths8[w{s}]", w8[s:s+32])
print("campaign v2 hits:", len(hits))
