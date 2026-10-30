#!/usr/bin/env python3
"""PZL11 stego v2 — FULL bitplane scan (gray+alpha) + Row-0 deep dive.

Complete scan: every 32-byte window of gray/alpha bit-planes (bits 0..2,
MSB/LSB first) -> derive ETH address -> compare to prize. Plus Row-0
watermark (cols 1013-1400) exhaustively.
"""
from PIL import Image
import numpy as np, time
from coincurve import PublicKey
from Crypto.Hash import keccak

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

arr = np.array(Image.open(IMG))
gray = arr[:, :, 0].astype(np.uint8)
alpha = arr[:, :, 1].astype(np.uint8)

def bitplane_bytes(u8bytes, bit, msb_first):
    bits = np.unpackbits(np.frombuffer(u8bytes, dtype=np.uint8),
                         bitorder='big' if msb_first else 'little')
    return np.packbits(bits >> bit).tobytes()

def full_scan(name, stream):
    n = len(stream) - 31
    hits = 0; t0 = time.time()
    for s in range(n + 1):
        if derive(stream[s:s+32]) == PRIZE:
            print(f"  *** MATCH *** {name} @byte {s}"); hits += 1
    print(f"  {name}: {n+1} windows, {hits} hit, {time.time()-t0:.1f}s")
    return hits

print("=== FULL gray/alpha bitplane scan (all windows) ===")
tot = 0
for ch_name, ch in [("gray", gray.tobytes()), ("alpha", alpha.tobytes())]:
    for bit in (0, 1):
        for mo in (True, False):
            tot += full_scan(f"{ch_name} bit{bit} {'msb' if mo else 'lsb'}",
                             bitplane_bytes(ch, bit, mo))
print("total bitplane hits:", tot)

print("\n=== Row 0 watermark deep dive ===")
r0 = gray[0, :]
nz = np.where(r0 != 255)[0]
vals = r0[nz]
print(f"cols {nz.min()}..{nz.max()}, {len(nz)} values")
def dv(name, b):
    a = derive(bytes(b))
    if a == PRIZE:
        print(f"  *** MATCH *** {name}"); return True
    return False
# every transform + window of row0 vals/cols and 255-minus
def seq_scan(name, seq):
    seq = bytes(np.asarray(seq, dtype=np.uint8).tolist())
    if dv(name+":full", seq[:32]) or dv(name+":last", seq[-32:]):
        return
    minus = bytes((255-b)&0xFF for b in seq)
    for s in range(len(seq)-31):
        if dv(f"{name}[w{s}]", seq[s:s+32]) or dv(f"{name}-m[w{s}]", minus[s:s+32]):
            return

seq_scan("row0_vals", vals)
seq_scan("row0_cols", nz)
seq_scan("row0_full", r0)
print("row0 done.")
