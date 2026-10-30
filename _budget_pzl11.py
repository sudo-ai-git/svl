import sys, os, hashlib, numpy as np, math
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
def eth_address(priv):
    pk = PublicKey.from_secret(priv).format(compressed=False)  # uncompressed SEC1
    return kc(pk)[12:]
def der(p):
    if len(p) != 32: return None
    n = int.from_bytes(p, 'big')
    if n == 0 or n >= ORDER: return None
    return eth_address(n.to_bytes(32,'big'))
hits=[]
def chk(name,b):
    if isinstance(b,bytes) and len(b)==32:
        a=der(b)
        if a==PRIZE: hits.append((name,b.hex()))
windows=[]
tested=set()
def windows(name, seq):
    seq=bytes(seq)
    for s in range(len(seq)-31):
        b=seq[s:s+32]
        if b in tested: continue
        tested.add(b)
        chk(f"{name}[w{s}]", b)
g=gray; a=alpha
# channel: gray values along the sail outline (434 px)
ys,xs=np.where(a<255); idx=np.lexsort((xs,ys))
av=a[ys[idx],xs[idx]].astype(np.uint8); gv=gray[ys[idx],xs[idx]].astype(np.uint8)
_allwindows=[]
windows("sail_alpha", bytes(av.tobytes()))
_allwindows.append(bytes(gv.tobytes()))
windows("sail_gray", bytes(gv.tobytes()))
# channel: row0 watermark (147 vals) - all windows
r0=g[0]; nz=np.where(r0!=255)[0]; rv=g[0,nz].astype(np.uint8)
_allwindows.append(bytes(rv.tobytes()))
windows("row0", bytes(rv.tobytes()))
__aef=np.array(rv,dtype=np.uint16).astype(">u2").byteswap().tobytes()
pass
_aef=np.array(rv,dtype=np.uint16).astype(">u2").byteswap().tobytes()
windows("row0LE", _aef)
_aef2=np.column_stack([av,gv]).ravel().astype(np.uint16).tobytes()
_aef2b=np.column_stack([gv,av]).ravel().astype(np.uint16).tobytes()
windows("sail_pair16LE_A2G", _aef2b)
windows("sail_pair16LE", _aef2)
_aef2b=np.column_stack([gv,av]).ravel().astype(np.uint16).tobytes()
windows("sail_pair16LE_rev", _aef2b)
windows("row0BE", _aef[::-1])
# channel: skyline top-edge per column (y of topmost gray<255 for y<600)
tops=[]
for x in range(W):
    col=g[:600,x]; nz=np.where(col<255)[0]
    if len(nz): tops.append(int(nz.min()))
_allwindows.append(bytes(np.array(tops,dtype=np.uint16).tobytes()))
windows("tops", bytes(np.array(tops,dtype=np.uint16).tobytes()))
_tef=np.array(tops,dtype=np.uint16).astype(">u2").byteswap().tobytes()
windows("topsLE", _tef)
windows("topsBE", _tef[::-1])
# channel: building heights 12
heights=[167,245,144,212,292,106,250,220,137,208,144,226]
_allwindows.append(bytes(np.array(heights,dtype=np.uint16).tobytes()))
windows("heights1", bytes(np.array(heights,dtype=np.uint16).tobytes()))
_hef=np.array(heights,dtype=np.uint16).astype(">u2").byteswap().tobytes()
windows("heights1LE", _hef)
windows("heights1BE", _hef[::-1])
_hwb=np.array(heights,dtype=np.uint16).astype(">u2").byteswap().tobytes()
for h,w in zip(heights,[217,96,86,91,176,99,107,97,159,111,97,100]):
    _hwb+=np.array([h,w],dtype=np.uint16).astype(">u2").byteswap().tobytes()
windows("hw16BE", _hwb)
_hwb2=np.array(heights,dtype=np.uint16).astype(">u2").byteswap().tobytes()
for h,w in zip(heights,[217,96,86,91,176,99,107,97,159,111,97,100]):
    _hwb2+=np.array([w,h],dtype=np.uint16).astype(">u2").byteswap().tobytes()
windows("hw16LE", _hwb2)
windows("heights1BE", _hef[::-1])
# channel: combined H,W 2-byte BE
hw=bytes()
for h,w in zip(heights,[217,96,86,91,176,99,107,97,159,111,97,100]):
    hw+=h.to_bytes(2,'big')+w.to_bytes(2,'big')
windows("hwBE", hw)
# channel: combined H,W 2-byte LE
hwle=bytes()
for h,w in zip(heights,[217,96,86,91,176,99,107,97,159,111,97,100]):
    hwle+=h.to_bytes(2,'little')+w.to_bytes(2,'little')
windows("hwLE", hwle)
# channel: 28-digit barcode
digits=[0,5,2,3,2,3,3,4,6,5,9,5,6,6,2,0,3,7,3,4,4,3,4,2,0,4,6,3]
windows("bar", bytes(digits))
# channel: landmark x alphas
for x in [11,43,154,314]: windows(f"land{x}", bytes([a[0,x]]))
print("total 32-byte chunks:", sum(len(w)-31 for w in _allwindows))
for w in _allwindows:
    for s in range(len(w)-31):
        b=w[s:s+32]
        if b in tested: continue
        tested.add(b)
        for hname,h in (("raw",b),("rev",b[::-1]),("sha256",hashlib.sha256(b).digest()),("keccak",kc(b))):
            if len(h)==32:
                aa=der(h)
                if aa==PRIZE:
                    print("*** HITCAND", hname, s, h.hex()); hits.append((f"{hname}:{s}",h.hex()))
print("tested unique:",len(tested))
print("hits:",len(hits))
for h in hits: print(" *** MATCH", h)
