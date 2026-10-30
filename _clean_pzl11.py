import sys, os, hashlib, numpy as np
from PIL import Image
from coincurve import PublicKey
from Crypto.Hash import keccak
IMG = "/home/sudosudo/.openclaw/workspace/pzl11.png"
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140
arr = np.array(Image.open(IMG)); gray = arr[:,:,0].astype(np.uint8); alpha = arr[:,:,1].astype(np.uint8)
H,W = gray.shape
def kc(b):
    h = keccak.new(digest_bits=256); h.update(b); return h.digest()
def eth_from_key(priv):
    pk = PublicKey.from_secret(priv).format(compressed=False)[1:]
    return kc(pk)[12:]
def der(p):
    if len(p) != 32: return None
    n = int.from_bytes(p, 'big')
    if n == 0 or n >= ORDER: return None
    return eth_from_key(p)
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
ys,xs=np.where(a<255); idx=np.lexsort((xs,ys))
av=a[ys[idx],xs[idx]].astype(np.uint8); cands.append(av.tobytes())
r0=g[0]; nz=np.where(r0!=255)[0]; rv=g[0,nz].astype(np.uint8)
cands.append(rv.tobytes()); cands.append((255-rv)&0xFF)
top16=[]
for x in range(W):
    col=g[:600,x]; nz=np.where(col<255)[0]
    if len(nz):
        yy=int(nz.min()); top16.append(yy%256); top16.append((yy+9)%256)
cands.append(np.array(top16,dtype=np.uint8).tobytes())
heights=[167,245,144,212,292,106,250,220,137,208,144,226]
cands.append(bytes(h%256 for h in heights))
cands.append(np.array(heights,dtype=np.uint16).tobytes())
hw=bytes()
for h,w in zip(heights,[217,96,86,91,176,99,107,97,159,111,97,100]):
    hw+=h.to_bytes(2,'big')+w.to_bytes(2,'big')
cands.append(hw)
digits=[0,5,2,3,2,3,3,4,6,5,9,5,6,6,2,0,3,7,3,4,4,3,4,2,0,4,6,3]
cands.append(bytes(digits)); cands.append(bytes(d+48 for d in digits))
for x in [11,43,154,314]: cands.append(bytes([a[0,x]]))
darkcol=(g<128).sum(axis=0).astype(np.uint8); cands.append(darkcol.tobytes())
darkrow=(g<128).sum(axis=1).astype(np.uint8); cands.append(darkrow.tobytes())
cands.append(g.tobytes()); cands.append(a.tobytes())
bits=[]
for v in av:
    for bit in range(5): bits.append((v>>bit)&1)
cands.append(bytes(bits))
comps=[]
for yy,xx in zip(ys,xs):
    comps.append(yy&0xFF); comps.append(xx&0xFF)
cands.append(bytes(comps))
gz=np.argwhere(g==0)[:2000]
cands.append(gz.astype(np.uint16).tobytes())
cands.append(rv.astype(np.uint16).tobytes())
# A: sample 32 (nearest-neighbor) from the 147 row-0 watermark values
idxs=np.linspace(0,len(rv)-1,32).astype(int)
cands.append(rv[idxs].astype(np.uint8).tobytes())
# B: whole-file raw bytes (1 byte per pixel row0) as windows + whole
cands.append(g[0].tobytes())
cands.append(g[0].tobytes().hex().encode())
cands.append(a[0].tobytes())
cands.append(a[0].tobytes().hex().encode())
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
        b=bytes(b)
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
