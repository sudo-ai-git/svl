#!/usr/bin/env python3
"""PZL11 solver v2 — feature-based extraction.

Findings so far:
 - gray channel = visible Chicago skyline + sailboat sketch
 - alpha<255 layer = sailboat outline (subtle), x0-551 y378-1102
 - prize address NOT present as hex ASCII anywhere
 - 4903 raw byte-extractions -> no address match

v2 targets FEATURES: Row 0 watermark (Jack's lead), skyline top profile,
building heights, and PNG metadata chunks. Each yields candidate 32-byte
private keys; we derive the Ethereum address and compare to the prize.
"""
from PIL import Image
import numpy as np
from coincurve import PublicKey
from Crypto.Hash import keccak
import struct

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140

def keccak256(b):
    h = keccak.new(digest_bits=256); h.update(b); return h.digest()

def derive(priv):
    if len(priv) != 32:
        return None
    n = int.from_bytes(priv, 'big')
    if n == 0 or n >= ORDER:
        return None
    try:
        return keccak256(PublicKey.from_secret(priv).format(compressed=False)[1:])[12:]
    except Exception:
        return None

assert derive((1).to_bytes(32, 'big')).hex() == '7e5f4552091a69125d5dfcb7b8c2659029395bdf'

img = Image.open(IMG)
arr = np.array(img)
gray = arr[:, :, 0].astype(np.uint8); alpha = arr[:, :, 1].astype(np.uint8)
H, W = gray.shape

candidates = []
def add(name, b):
    if isinstance(b, np.ndarray):
        b = b.tobytes()
    if isinstance(b, (bytes, bytearray)) and len(b) == 32:
        candidates.append((name, bytes(b)))

def derive_check(name, b):
    a = derive(b)
    if a == PRIZE:
        print(f"  *** MATCH *** {name} -> {a.hex()}")
        return True
    return False

# ---------- PNG metadata chunks ----------
print("=== PNG chunks ===")
raw = open(IMG, 'rb').read()
print("PIL info keys:", list(img.info.keys()))
# parse chunks for text
i = 8
texts = []
while i < len(raw) - 8:
    ln = struct.unpack('>I', raw[i:i+4])[0]; typ = raw[i+4:i+8]
    data = raw[i+8:i+8+ln]
    if typ in (b'tEXt', b'iTXt', b'zTXt'):
        texts.append((typ.decode(), data[:200]))
    i += 12 + ln
    if typ == b'IEND':
        break
print("text chunks:", [(t, d[:60]) for t, d in texts] if texts else "none")

# ---------- Row 0 watermark ----------
print("\n=== Row 0 watermark ===")
r0 = gray[0, :]
nz = np.where(r0 != 255)[0]
print(f"non255 count={len(nz)} cols[{nz.min()},{nz.max()}]")
vals = r0[nz]
print("values[:40]:", vals[:40].tolist())
print("cols[:40]:", nz[:40].tolist())
# try many interpretations of row0
def seq_variants(name, seq):
    seq = bytes(seq.astype(np.uint8).tolist()) if isinstance(seq, np.ndarray) else bytes(seq)
    add(f"{name}:full", seq); add(f"{name}:first32", seq[:32]); add(f"{name}:last32", seq[-32:])
    minus = bytes((255 - b) & 0xFF for b in seq)
    add(f"{name}:255m:first32", minus[:32]); add(f"{name}:255m:last32", minus[-32:])
    if len(seq) >= 64:
        add(f"{name}:nibble", bytes(((seq[i] & 0xF) << 4) | (seq[i+1] & 0xF) for i in range(0, 64, 2)))
    if len(seq) >= 256:
        bits = ''.join(str(b & 1) for b in seq[:256]); add(f"{name}:lsb", int(bits, 2).to_bytes(32, 'big'))
    # all 32-windows (bounded)
    n = len(seq)
    for s in range(0, max(1, n - 31), max(1, (n - 31) // 3000)):
        add(f"{name}:w{s}", seq[s:s+32])

seq_variants("row0_vals", vals)
seq_variants("row0_cols", nz)
seq_variants("row0_full", r0)

# ---------- Skyline top profile ----------
print("\n=== Skyline profile ===")
# top edge: first row per column where gray < 120
profile = np.full(W, -1, dtype=np.int64)
for c in range(W):
    rows = np.where(gray[:, c] < 120)[0]
    if len(rows):
        profile[c] = rows[0]
good = profile[profile >= 0]
print(f"profile columns={len(good)} min/max y={good.min() if len(good) else None}/{good.max() if len(good) else None}")
# building top as bytes (y offsets), and heights from a baseline
base = int(good.max()) if len(good) else 0
heights = (base - good[good >= 0]).astype(np.uint8)
seq_variants("skyline_top", good.astype(np.int64))
seq_variants("skyline_h", heights)

# ---------- run ----------
print(f"\n=== derive/check {len(candidates)} candidates ===")
seen = set(); hits = 0
for name, b in candidates:
    if b in seen:
        continue
    seen.add(b)
    if derive_check(name, b):
        hits += 1
print(f"done. {hits} match(es), {len(seen)} unique.")
