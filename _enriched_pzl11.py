import sys, os, hashlib, numpy as np
from PIL import Image
from coincurve import PublicKey
from Crypto.Hash import keccak
_pkg = os.path.join('/home/sudosudo/.openclaw/workspace', 'venv_pkg')
if _pkg not in sys.path: sys.path.insert(0, _pkg)
from eth_account import Account
IMG = '/home/sudosudo/.openclaw/workspace'+'pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
arr = np.array(Image.open(IMG)); gray = arr[:,:,0].astype(np.uint8); alpha = arr[:,:,1].astype(np.uint8)
H,W = gray.shape
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
cands=[]
g=gray; a=alpha
# 1 sail outline alpha
ys,xs=np.where(a<255); idx=np.lexsort((xs,ys))
av=a[ys[idx],xs[idx]].astype(np.uint8); cands.append(av.tobytes())
# 2 row0 watermark
r0=g[0]; nz=np.where(r0!=255)[0]; rv=g[0,nz].astype(np.uint8)
cands.append(rv.tobytes()); cands.append((255-rv)&0xFF); cands.append(rv.astype(np.uint16).tobytes())
# 3 skyline top-edge as a 16-bit curve per column (y of topmost gray<255 for y<600)
top16=[]
for x in range(W):
    col=g[:600,x]; nz=np.where(col<255)[0]
    if len(nz): top16.append(int(col[nz.argmin()]+256*g[nz.argmin()+1,x] if False else 0))
# proper: use two rows: y for high byte, top+1 for low byte
top16=[]
for x in range(W):
    col=g[:600,x]; nz=np.where(col<255)[0]
    if len(nz):
        yy=int(nz.min())
        top16.append(yy); top16.append(min(yy+1,600))
cands.append(np.array(top16,dtype=np.uint8).tobytes())
# 4 building heights 12
heights=[167,245,144,212,292,106,250,220,137,208,144,226]
cands.append(bytes(h%256 for h in heights))
cands.append(np.array(heights,dtype=np.uint16).tobytes())
# 5 combined H/W 2-byte
hw=bytes()
for h,w in zip(heights,[217,96,86,91,176,99,107,97,159,111,97,100]):
    hw+=h.to_bytes(2,'big')+w.to_bytes(2,'big')
cands.append(hw)
# 6 28 digit
digits=[0,5,2,3,2,3,3,4,6,5,9,5,6,6,2,0,3,7,3,4,4,3,4,2,0,4,6,3]
cands.append(bytes(digits)); cands.append(bytes(d+48 for d in digits))
# 7 landmark x alphas
for x in [11,43,154,314]: cands.append(bytes([a[0,x]]))
# 8 dark area per column
darkcol=(g<128).sum(axis=0).astype(np.uint8); cands.append(darkcol.tobytes())
# 9 gray=0 pixel count per row (row darkness profile)
darkrow=(g<128).sum(axis=1).astype(np.uint8); cands.append(darkrow.tobytes())
# 10 full raster windows gray and alpha
cands.append(g.tobytes()); cands.append(a.tobytes())
# 11 alpha 5-bit packed, all windows
bits=[]
for v in av:
    for bit in range(5): bits.append((v>>bit)&1)
cands.append(bytes(bits))
# 12 component positions (x,y) 2-byte
comps=[]
for yy,xx in zip(ys,xs):
    comps.append(yy&0xFF); comps.append(xx&0xFF)
cands.append(bytes(comps))
# 13 gray=0 pixel list x,y as 2-byte
gz=np.argwhere(g==0)
cands.append(gz.astype(np.uint16).tobytes()[:4000])
# 14 row0 watermark cols+vals as 2-byte
cands.append(rv.astype(np.uint16).tobytes())
# 15 2-byte LE heights, widths
hwle=bytes()
for h,w in zip(heights,[217,96,86,91,176,99,107,97,159,111,97,100]):
    hwle+=h.to_bytes(2,'little')+w.to_bytes(2,'little')
cands.append(hwle)
tested=set()
print("total 32-byte chunks:", sum(max(0,len(c)-31) for c in cands))
for ci,c in enumerate(cands):
    if len(c)<32: continue
    for off in range(0,len(c)-31):
        b=c[off:off+32]
        if b in tested: continue
        tested.add(b)
        for hname,h in (("raw",b),("rev",b[::-1]),("sha256",hashlib.sha256(b).digest()),("keccak",kc(b))):
            if len(h)==32:
                aa=der(h)
                if aa==PRIZE:
                    print("*** HITCAND", ci, hname, off, h.hex()); hits.append((f"{ci}:{hname}:{off}",h.hex()))
print("tested unique:",len(tested))
print("hits:",len(hits))
for h in hits: print(" *** MATCH", h)
