#!/usr/bin/env python3
import numpy as np, hashlib, math
from PIL import Image
from eth_account import Account
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
arr = np.array(Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png'))
g = arr[:,:,0].astype(np.uint8); a = arr[:,:,1].astype(np.uint8)

def oracle_bit(b):
    try:
        return Account.from_key(b).address.lower()==PRIZE.lower()
    except:
        return False

# E1: photo_cos2 alpha on sail
ys,xs = np.where(a<255)
al = a[ys,xs].astype(np.float64); gr = g[ys,xs].astype(np.float64)
for tA,tB,ph in [(167,245,144),(167,245,106),(167,245,212),(292,106,144)]:
    I = np.cos((ph + tA*al + tB*gr)/2.0)**2
    for inv in [0,1]:
        kb = ((I>=0.5).astype(np.uint8) ^ inv).astype(np.uint8)
        if len(kb)==32 and oracle_bit(kb):
            print("PHOTO_COS2 HIT tA=%s tB=%s ph=%s inv=%s" % (tA,tB,ph,inv))
print("E1 done")
# E2: gate params from heights; test thetaA,thetaB,phi0 over a grid using INV=0/1
#    note: invert from 5th height = 292 -> 292&1 = 0 ; from 12th = 226 -> 0
INV = [0,1]
for tA in [167, 245, 144, 212, 292, 106, 250, 220, 137, 208, 144, 226]:
    for tB in [167, 245, 144, 212, 292, 106, 250, 220, 137, 208, 144, 226]:
        for phi0 in [167, 245, 144, 212, 292, 106, 250, 220, 137, 208, 144, 226]:
            for inv in INV:
                I = np.cos((phi0 + tA*al + tB*gr)/2.0)**2
                kb = ((I>=0.5).astype(np.uint8) ^ inv).astype(np.uint8)
                if len(kb)==32 and oracle_bit(kb):
                    print("GATE_HIT thetaA=%s thetaB=%s phi0=%s inv=%s" % (tA,tB,phi0,inv))
print("E2 done")
