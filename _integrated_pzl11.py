
import sys, os, hashlib, numpy as np
from PIL import Image
from coincurve import PublicKey
from Crypto.Hash import keccak
# fix sys.path: venv_pkg first
_pkg = os.path.join('/home/sudosudo/.openclaw/workspace', 'venv_pkg')
if _pkg not in sys.path: sys.path.insert(0, _pkg)
from eth_account import Account
IMG = '/home/sudosudo/.openclaw/workspace'+'pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
arr = np.array(Image.open(IMG)); gray = arr[:,:,0].astype(np.uint8); alpha = arr[:,:,1].astype(np.uint8)

def kc(b):
    h = keccak.new(digest_bits=256); h.update(b); return h.digest()
def der(p):
    if len(p) != 32: return None
    n = int.from_bytes(p, 'big')
    if n == 0 or n >= ORDER: return None
    try: return kc(PublicKey.from_secret(p).format(compressed=False)[1:])[12:]
    except Exception: return None
hits=[]
def chk(name,b):
    if isinstance(b,bytes) and len(b)==32:
        a=der(b)
        if a==PRIZE: hits.append((name,b.hex()))
def windows(name, seq):
    seq=bytes(seq)
    for s in range(len(seq)-31):
        chk(f"{name}[w{s}]", seq[s:s+32])
# build candidate list of 32-byte keys from many channels
cands=[]
g=gray; a=alpha; H,W=g.shape
# 1. sail outline alpha (434 px)
ys,xs=np.where(a<255)
idx=np.lexsort((xs,ys))
av=a[ys[idx],xs[idx]].astype(np.uint8)
cands.append(av.tobytes())
# 2. row0 watermark vals (147)
r0=g[0]; nz=np.where(r0!=255)[0]; rv=g[0,nz].astype(np.uint8)
cands.append(rv.tobytes())
cands.append((255-rv)&0xFF)
# 3. skyline profile (building tops): for each x, topmost gray<255 row in y<600
tops=[]
for x in range(W):
    col=g[:600,x]
    nz=np.where(col<255)[0]
    if len(nz): tops.append(int(col.min()))
cands.append(np.array(tops,dtype=np.uint8).tobytes())
# 4. building heights 12
heights=[167,245,144,212,292,106,250,220,137,208,144,226]
cands.append(bytes(h%256 for h in heights))
# 5. combined H,W pairs (2-byte BE)
hw=bytes()
for h,w in zip(heights,[217,96,86,91,176,99,107,97,159,111,97,100]):
    hw+=h.to_bytes(2,'big')+w.to_bytes(2,'big')
cands.append(hw)
# 6. 28-digit barcode sequence
digits=[0,5,2,3,2,3,3,4,6,5,9,5,6,6,2,0,3,7,3,4,4,3,4,2,0,4,6,3]
cands.append(bytes(digits))
cands.append(bytes(d+48 for d in digits))
# 7. alpha at landmark x positions (11,43,154,314)
for x in [11,43,154,314]:
    cands.append(bytes([a[0,x]]))
# 8. gray=0 pixel count per column (dark area) -> 1600 bytes
darkcol=(g<128).sum(axis=0).astype(np.uint8)
cands.append(darkcol.tobytes())
# 9. longest-run tops per column (skyline peaks)
tops2=[]
for x in range(W):
    col=g[:600,x]
    nz=np.where(col<255)[0]
    if len(nz): tops2.append(int(nz.min()))
cands.append(np.array(tops2,dtype=np.uint8).tobytes())
tested=set()
print("total candidate 32-byte chunks:", sum(max(0,len(c)-31) for c in cands))
for ci,c in enumerate(cands):
    if len(c)<32: continue
    for off in range(0, len(c)-31):
        b=c[off:off+32]
        if b in tested: continue
        tested.add(b)
        for nm,bb in ((ci,)+("",)):
            pass
        for hname,h in (("raw",b),("rev",b[::-1]),("sha256",hashlib.sha256(b).digest()),("keccak",kc(b))):
            if hname in ("raw",):
                pass
            if len(h)==32:
                for tryb in (h,):
                    aa=der(tryb)
                    if aa==PRIZE:
                        print("*** HITCAND", ci, hname, off, tryb.hex()); hits.append((f"{ci}:{hname}:{off}",tryb.hex()))
print("tested unique:",len(tested))
print("hits:",len(hits))
for h in hits: print(" *** MATCH", h)
