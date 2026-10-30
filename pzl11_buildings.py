#!/usr/bin/env python3
"""PZL11 — 12-buildings lead (community) + 'ArweaveP' string.

Community measured exactly 12 buildings; hypothesized a BIP39 12-word seed.
Measure the towers precisely, then test: heights/widths as bytes; heights ->
BIP39 word indices -> mnemonic -> seed -> BIP32 master key -> address; and the
'twitter.com/ArweaveP' string hashed.
"""
from PIL import Image
import numpy as np, hmac, hashlib, unicodedata
from coincurve import PublicKey
from Crypto.Hash import keccak

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
WORDS = [w.strip() for w in open('/home/sudosudo/.openclaw/workspace/bip39_english.txt')]
assert len(WORDS) == 2048

def keccak256(b):
    h = keccak.new(digest_bits=256); h.update(b); return h.digest()
def der(p):
    if len(p) != 32: return None
    n = int.from_bytes(p, 'big')
    if n == 0 or n >= ORDER: return None
    try: return keccak256(PublicKey.from_secret(p).format(compressed=False)[1:])[12:]
    except Exception: return None
def chk(name, b):
    if isinstance(b, np.ndarray): b = b.tobytes()
    if isinstance(b, (bytes, bytearray)) and len(b) == 32:
        a = der(bytes(b))
        if a == PRIZE: print("  *** MATCH ***", name, bytes(b).hex())
        return a
    return None
def bip39_seed(mnemonic_words, passphrase=""):
    m = unicodedata.normalize("NFKD", " ".join(mnemonic_words))
    s = unicodedata.normalize("NFKD", "mnemonic" + passphrase)
    return hashlib.pbkdf2_hmac("sha512", m.encode(), s.encode(), 2048, 64)

arr = np.array(Image.open(IMG)); gray = arr[:, :, 0].astype(np.uint8); H, W = gray.shape
hits = []

# --- measure top edge + horizon ---
top = np.full(W, H, dtype=np.int64)
for c in range(W):
    r = np.nonzero(gray[:, c] < 128)[0]
    if len(r): top[c] = r[0]
darkfrac = (gray < 128).mean(axis=1)
# horizon = shallowest row still >0.5 dark (ground surface)
hor = int(np.max(np.nonzero(darkfrac > 0.5)))
print(f"horizon ~ {hor}, image H={H}")
heights_all = np.clip(hor - top, 0, None)

# --- segment buildings: runs where top < hor-15 ---
present = top < (hor - 15)
runs = []; i = 0
while i < W:
    if present[i]:
        j = i
        while j < W and present[j]: j += 1
        runs.append((i, j - 1)); i = j
    else: i += 1
print(f"coarse runs (hor-15): {len(runs)}")
# merge tiny gaps to stabilize ~12
def segment(minw=20, gap=15):
    runs = []; i = 0
    while i < W:
        if present[i]:
            j = i
            while j < W:
                if present[j]: j += 1
                elif j - i >= minw and (j + gap <= W and present[j+1] if j+1 < W else False): j += 1
                else: break
            runs.append((i, j - 1)); i = j
        else: i += 1
    return runs
runs = segment()
print(f"segmented buildings: {len(runs)}")
heights = []; widths = []
for (i, j) in runs:
    heights.append(int(hor - top[i:j+1].max()))
    widths.append(j - i + 1)
print("heights:", heights)
print("widths :", widths)

# --- test heights/widths as bytes ---
for label, seq in [("heights", heights), ("widths", widths)]:
    s8 = np.array(seq, dtype=np.uint8).tobytes() if max(seq) < 256 else None
    if s8:
        chk(f"{label}8:first", s8[:32]); chk(f"{label}8:last", s8[-32:])
        for k in range(len(s8)-31): chk(f"{label}8[w{k}]", s8[k:k+32])
    s2 = b''.join(x.to_bytes(2, 'big') for x in seq)
    s2l = b''.join(x.to_bytes(2, 'little') for x in seq)
    chk(f"{label}16be:first", s2[:32]); chk(f"{label}16le:first", s2l[:32])
    for k in range(len(s2)-31): chk(f"{label}16be[w]", s2[k:k+32])
    for k in range(len(s2l)-31): chk(f"{label}16le[w]", s2l[k:k+32])

# --- BIP39: heights -> word index -> mnemonic -> seed -> master key ---
n = len(heights)
def mnemonic_from_indices(idxs):
    return [WORDS[i % 2048] for i in idxs]
def test_mnemonic(mw, tag):
    seed = bip39_seed(mw)
    master = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()[:32]
    chk(f"{tag}:seed[:32]", seed[:32])
    chk(f"{tag}:seed[32:]", seed[32:])
    chk(f"{tag}:master", master)
    # also joined ascii padded
    asc = "".join(mw).encode()[:32]
    asc = asc + b"\x00" * (32 - len(asc)) if len(asc) <= 32 else asc[:32]
    chk(f"{tag}:mnemonic-ascii", asc)

if n == 12:
    for scaler in [1, 8, 2047/max(heights) if max(heights) else 1]:
        idxs = [int(h*scaler) for h in heights]
        test_mnemonic(mnemonic_from_indices(idxs), f"h-idx*s{scaler:g}")
        idxs2 = [2047 - i for i in idxs]
        test_mnemonic(mnemonic_from_indices(idxs2), f"h-idx*s{scaler:g}-rev")
    # rank-based indices
    order = sorted(range(n), key=lambda k: heights[k])
    ranks = [0]*n
    for r, k in enumerate(order): ranks[k] = r
    test_mnemonic(mnemonic_from_indices([r*186 for r in ranks]), "rank*186")
    # widths as indices
    test_mnemonic(mnemonic_from_indices([w*9 for w in widths]), "width*9")
    # heights+widths interleaved
    hw = []
    for k in range(n): hw += [heights[k], widths[k]]
    test_mnemonic(mnemonic_from_indices([x*8 for x in hw[:12]]), "h+w*8")

# --- 'twitter.com/ArweaveP' string ---
for s in ["https://twitter.com/ArweaveP", "twitter.com/ArweaveP", "twitter.com/arweavep",
          "ArweaveP", "https://twitter.com/ArweaveP/", "@ArweaveP"]:
    b = s.encode()
    chk(f"str:{s}:sha256", hashlib.sha256(b).digest())
    chk(f"str:{s}:keccak", keccak256(b))
    chk(f"str:{s}:ascii", (b + b"\x00"*32)[:32])

print("buildings campaign hits:", len(hits))
