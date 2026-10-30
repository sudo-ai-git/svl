#!/usr/bin/env python3
"""PZL11 stego scan — look for a 32-byte private key embedded in pixel bitplanes.

A stego-puzzle key is most often in the LSB/bitplane layer. We extract bit
planes of gray and alpha (row-major), pack to bytes (MSB-first and LSB-first),
slide 32-byte windows, derive the Ethereum address, and compare to the prize.
Also renders the low bitplanes so any hidden text/shape is visible.
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

img = Image.open(IMG).convert('L')  # gray only for the primary scan
g = np.array(img).astype(np.uint8).tobytes()
print(f"gray bytes: {len(g)}")

def bitplane(data, bit, msb_first=True):
    """Extract `bit` from each byte -> pack bits into a byte stream."""
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8), bitorder='big' if msb_first else 'little')
    bits = bits >> bit
    return np.packbits(bits).tobytes()

def scan(name, stream, maxw=120000):
    n = len(stream) - 32
    hits = 0; t0 = time.time()
    for s in range(0, max(1, n + 1), max(1, (n) // maxw)):
        a = derive(stream[s:s+32])
        if a == PRIZE:
            print(f"  *** MATCH *** {name} @byte {s*8+bit} (bit offset ~{s})"); hits += 1
    print(f"  {name}: scanned {min(n,maxw)} windows in {time.time()-t0:.1f}s, {hits} hit")
    return hits

# cheap: first/last 32 bytes of each low bitplane
print("\n=== cheap: bitplane edges ===")
for bit in (0, 1, 2):
    for mo in (True, False):
        bp = bitplane(g, bit, mo)
        for tag, b in [("first", bp[:32]), ("last", bp[-32:])]:
            if derive(b) == PRIZE:
                print(f"  *** MATCH gray bit{bit} {mo} {tag}")

print("\n=== window scan (timed, bounded) ===")
total = 0
for bit in (0, 1):
    for mo in (True, False):
        bp = bitplane(g, bit, mo)
        total += scan(f"gray bit{bit} {'msb' if mo else 'lsb'}", bp)
print(f"total hits: {total}")
print("(If nothing: key is not a raw 32-byte key in gray LSBs, or it's a seed/mnemonic/other form.)")
