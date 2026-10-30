#!/usr/bin/env python3
import numpy as np, hashlib, math
from PIL import Image
from eth_account import Account
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
arr = np.array(Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png'))
g = arr[:,:,0].astype(np.uint8); a = arr[:,:,1].astype(np.uint8)

# 1) photo_cos2 on the sail alpha, gate params from heights
thetaA, thetaB, phi0 = 167.0, 245.0, 144.0
inv = 212 & 1
ys, xs = np.where(a<255)
al = a[ys,xs].astype(np.float64); gr = g[ys,xs].astype(np.float64)
I = np.cos((phi0 + thetaA*al + thetaB*gr)/2.0)**2
bit = ((I>=0.5).astype(np.uint8) ^ invert).astype(np.uint8)
kb = bytes(bit)
print("photo_cos2 alpha: keybytes", len(kb), "hits:", Account.from_key(kb).address.lower()==PRIZE.lower() if len(kb)==32 else False)

# 2) gate params as 4 bytes (from first 4 heights) + 28-byte nonce
seq = PH[:4]
k4 = bytes(seq) + b'\x00'*28
print("gate4:", len(k4), "hits:", Account.from_key(k4).address.lower()==PRIZE.lower() if len(k4)==32 else False)
