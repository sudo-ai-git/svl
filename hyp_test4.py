#!/usr/bin/env python3
import hashlib, struct
from eth_account import Account
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
HEIGHTS = [167,245,144,212,292,106,250,220,137,208,144,226]
MNEM = "belt burger bamboo box cause ask butter breeze bachelor borrow bamboo brisk"

def ok(b):
    if len(b)!=32: return False
    try: return Account.from_key(b).address.lower()==PRIZE.lower()
    except: return False

tests = []

# 1) sha256 of the phrase text
h = hashlib.sha256(MNEM.encode()).digest()
tests.append(("phrase_sha256", h, ok(h)))

# 2) heights as raw bytes (8-bit each, zero-padded) 
k = bytes([x & 0xFF for x in HEIGHTS]) + b'\x00'*(32-len(HEIGHTS))
tests.append(("heights_raw8", k, ok(k)))

# 3) heights as 2-byte pairs (16-bit each) -> 24 bytes, zero-padded
k2 = b''.join(struct.pack('>H', x) for x in HEIGHTS)
tests.append(("heights_2byte", k2, ok(k2[:32].ljust(32, b'\x00'))))

# 4) sha256 of the height list
h2 = hashlib.sha256(bytes([x & 0xFF for x in HEIGHTS])).digest()
tests.append(("height_sha256", h2, ok(h2)))

# 5) phrase as UTF-8 bytes, zero-padded to 32
k3 = MNEM.encode('utf-8') + b'\x00'*(32-len(MNEM.encode('utf-8')))
tests.append(("phrase_utf8", k3, ok(k3)))

# 6) phrase as words concatenated without spaces, zero-padded
k4 = ''.join(MNEM.split()).encode() + b'\x00'*(32-len(''.join(MNEM.split()).encode()))
tests.append(("phrase_nospace", k4, ok(k4)))

# 7) heights as little-endian 2-byte pairs
k5 = b''.join(struct.pack('<H', x) for x in HEIGHTS)
tests.append(("heights_2byte_le", k5, ok(k5[:32].ljust(32, b'\x00'))))

for name, data, hit in tests:
    print(f"{name:20s} -> hits: {hit}  {data.hex()}")
