#!/usr/bin/env python3
"""PZL11 solver harness.

Win condition: a private key hidden in pzl11.png derives to the prize address
0xff2142e98e09b5344994f9beb9c56c95506b9f17 (holds 1 ETH).

Two tracks:
  A) ASCII/text search — does the prize address (or its bytes) appear in any
     channel or PNG metadata chunk? (the moltbook writeup says the address is
     readable as text; the private key is the hard part)
  B) candidate private-key sweep — generate bounded 32-byte candidates from
     extraction hypotheses, derive each Ethereum address, compare to the prize.

Crypto verified against known vectors (privkey=1 -> 7e5f45..., privkey=2 -> 2b5ad5...).
"""
from PIL import Image
import numpy as np
from coincurve import PublicKey
from Crypto.Hash import keccak

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
CURVE_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140

def keccak256(b):
    h = keccak.new(digest_bits=256); h.update(b); return h.digest()

def derive_address(priv):
    if len(priv) != 32:
        return None
    n = int.from_bytes(priv, 'big')
    if n == 0 or n >= CURVE_ORDER:
        return None
    try:
        pk = PublicKey.from_secret(priv)
        return keccak256(pk.format(compressed=False)[1:])[12:]
    except Exception:
        return None

# ---- self-test ----
assert derive_address((1).to_bytes(32, 'big')).hex() == '7e5f4552091a69125d5dfcb7b8c2659029395bdf'
assert derive_address((2).to_bytes(32, 'big')).hex() == '2b5ad5c4795c026514f8317c7a215e218dccd6cf'
print("crypto self-test PASS")

img = Image.open(IMG)
arr = np.array(img)
gray = arr[:, :, 0].astype(np.uint8)
alpha = arr[:, :, 1].astype(np.uint8)
H, W = gray.shape
print(f"image {W}x{H}, gray[{gray.min()},{gray.max()}] alpha[{alpha.min()},{alpha.max()}]")

candidates = []  # (name, bytes)

def add(name, b):
    if isinstance(b, np.ndarray):
        b = b.tobytes()
    if isinstance(b, (bytes, bytearray)) and len(b) == 32:
        candidates.append((name, bytes(b)))

# ---------- TRACK A: ASCII address search ----------
print("\n=== TRACK A: ASCII search for prize address / bytes ===")
addr_ascii = PRIZE.hex().encode()            # b'ff2142e9...'
addr_ascii_up = addr_ascii.upper()
for raw_name, raw in [("gray", gray.tobytes()), ("alpha", alpha.tobytes()),
                      ("raw_file", open(IMG, 'rb').read())]:
    for pat, label in [(addr_ascii, "addr-hex lc"), (addr_ascii_up, "addr-hex UC")]:
        i = raw.find(pat)
        print(f"  {raw_name}: {label} -> {'FOUND @' + str(i) if i >= 0 else 'no'}")
# per-row / per-col ASCII of gray
for r in range(H):
    if gray[r, :].tobytes().find(addr_ascii) >= 0:
        print(f"  gray row {r}: addr-hex FOUND")
for c in range(W):
    if gray[:, c].tobytes().find(addr_ascii) >= 0:
        print(f"  gray col {c}: addr-hex FOUND")

# ---------- candidate sources ----------
g_non255 = gray[gray != 255]
a_non255 = alpha[alpha != 255]
mask = alpha < 255
g_at_a = gray[mask]
a_at_a = alpha[mask]
row0 = gray[0, :]
col0 = gray[:, 0]
row0_n = row0[row0 != 255]
col0_n = col0[col0 != 255]

def windows(seq, name, maxw=4000):
    """All 32-length windows of seq (bounded)."""
    if isinstance(seq, np.ndarray):
        seq = seq.tobytes()
    n = len(seq)
    for s in range(0, max(0, n - 32 + 1), max(1, (n - 32 + 1) // maxw)):
        add(f"{name}[w@{s}]", seq[s:s + 32])

def variants(name, seq):
    """Generate 32-byte candidates from a byte sequence via common transforms."""
    if isinstance(seq, np.ndarray):
        seq = seq.astype(np.uint8).tobytes()
    seq = bytes(seq)
    add(f"{name}:full", seq)
    add(f"{name}:first32", seq[:32])
    add(f"{name}:last32", seq[-32:])
    # 255-minus
    minus = bytes((255 - b) & 0xFF for b in seq)
    add(f"{name}:255-minus", minus)
    add(f"{name}:255-minus:first32", minus[:32])
    # low nibble pack (needs even count)
    if len(seq) >= 64:
        packed = bytes(((seq[i] & 0xF) << 4) | (seq[i + 1] & 0xF) for i in range(0, 64, 2))
        add(f"{name}:nibble", packed)
    # LSBs -> 32 bytes from 256 bits
    if len(seq) >= 256:
        bits = ''.join(str(b & 1) for b in seq[:256])
        add(f"{name}:lsb256", int(bits, 2).to_bytes(32, 'big'))

for nm, seq in [
    ("g_non255", g_non255), ("a_non255", a_non255),
    ("g_at_a", g_at_a), ("a_at_a", a_at_a),
    ("row0_n", row0_n), ("col0_n", col0_n),
    ("row0_full", row0), ("col0_full", col0),
]:
    variants(nm, seq)
    windows(seq, nm)

print(f"\n=== TRACK B: {len(candidates)} candidate private keys ===")
hits = 0
seen = set()
for name, b in candidates:
    if b in seen:
        continue
    seen.add(b)
    addr = derive_address(b)
    if addr == PRIZE:
        print(f"  *** MATCH *** {name} -> {addr.hex()}")
        hits += 1
print(f"done. {hits} match(es), checked {len(seen)} unique candidates.")
