#!/usr/bin/env python3
"""PZL11 — community's exact leads, tested against the prize address.

Community (HomelessPhD/AR_Puzzles/PZL11 README) measured 12 buildings and
hypothesized a BIP39 seed. Test their EXACT numbers through every encoding,
plus BIP39 seed -> key derivations. Also the row-0 watermark, exhaustively.
"""
import hmac, hashlib, unicodedata
from coincurve import PublicKey
from Crypto.Hash import keccak

PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
WORDS = [w.strip() for w in open('/home/sudosudo/.openclaw/workspace/bip39_english.txt')]

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
def seed(mw, pp=""):
    m = unicodedata.normalize("NFKD", " ".join(mw)); s = unicodedata.normalize("NFKD", "mnemonic"+pp)
    return hashlib.pbkdf2_hmac("sha512", m.encode(), s.encode(), 2048, 64)

# --- community's exact building measurements ---
H12 = [100,190,90,165,240,55,180,160,90,160,100,190]
W12 = [115,90,100,170,100,100,150,110,110,100,70,50]

def bytefamily(name, vals):
    u8 = bytes(v & 0xFF for v in vals)
    chk(name+":u8[:32]", u8[:32]); chk(name+":u8[-32:]", u8[-32:])
    u16b = b''.join(v.to_bytes(2,'big') for v in vals)
    u16l = b''.join(v.to_bytes(2,'little') for v in vals)
    chk(name+":u16be[:32]", u16b[:32]); chk(name+":u16le[:32]", u16l[:32])
    # concat as one big int (all heights then widths), take 32-byte windows
    for combo_name, combo in [(name+":hw", H12+W12)]:
        total = 0
        for v in combo: total = (total << 16) | (v & 0xFFFF)
        tb = total.to_bytes((total.bit_length()+7)//8, 'big')
        tb = b'\x00'*(32-len(tb)) + tb if len(tb) < 32 else tb
        chk(combo_name, tb[-32:]); chk(combo_name+"[:32]", tb[:32])
        for s in range(len(tb)-31): chk(f"{combo_name}[w{s}]", tb[s:s+32])

bytefamily("H12", H12); bytefamily("W12", W12)

# --- BIP39: 12 buildings -> 12 word indices -> mnemonic -> seed -> key ---
def test_mn(mw, tag):
    sd = seed(mw)
    chk(f"{tag}:seed[:32]", sd[:32]); chk(f"{tag}:seed[32:]", sd[32:])
    master = hmac.new(b"Bitcoin seed", sd, hashlib.sha512).digest()[:32]
    chk(f"{tag}:master", master)
    asc = "".join(mw).encode()
    chk(f"{tag}:ascii", (asc + b"\x00"*(32-len(asc))) if len(asc)<=32 else asc[:32])

for tag, idxs in [
    ("h=idx", H12),
    ("h*8", [h*8 for h in H12]),
    ("h*9", [h*9 for h in H12]),
    ("h*16", [h*16 for h in H12]),
    ("h-rev", [2047-h for h in H12]),
    ("w=idx", W12),
    ("w*9", [w*9 for w in W12]),
    ("h+wranks", []),
]:
    if idxs:
        test_mn([WORDS[i % 2048] for i in idxs], tag)

# rank-based (tallest->0)
order = sorted(range(12), key=lambda k: H12[k])
ranks = [0]*12
for r, k in enumerate(order): ranks[k] = r
test_mn([WORDS[r] for r in ranks], "h-rank")
test_mn([WORDS[2047-r] for r in ranks], "h-rank-rev")

# --- row-0 watermark exhaustive ---
from PIL import Image
import numpy as np
gray = np.array(Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png'))[:, :, 0].astype(np.uint8)
r0 = gray[0, :]; nz = np.where(r0 != 255)[0]; vals = r0[nz].tolist()
def seq_all(name, seq):
    seq = bytes(int(v) & 0xFF for v in seq)
    chk(name+":first32", seq[:32]); chk(name+":last32", seq[-32:])
    minus = bytes((255 - v) & 0xFF for v in seq)
    chk(name+"-m:first32", minus[:32])
    for s in range(len(seq)-31):
        chk(f"{name}[w{s}]", seq[s:s+32]); chk(f"{name}-m[w{s}]", minus[s:s+32])
    # differences
    diff = bytes(((seq[(s+1)%len(seq)] - seq[s]) & 0xFF) for s in range(len(seq)))
    chk(name+":diff:first32", diff[:32])
seq_all("row0", vals)
seq_all("row0_255m", [255-v for v in vals])

print("community campaign hits:", len(hits))
