#!/usr/bin/env python3
import numpy as np, hashlib, math
from PIL import Image
from eth_account import Account
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
arr = np.array(Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png'))
g = arr[:,:,0].astype(np.uint8); a = arr[:,:,1].astype(np.uint8)
def oracle(b):
    if len(b)!=32: return False
    try: return Account.from_key(b).address.lower()==PRIZE.lower()
    except: return False
# photo_cos2 over whole image (all pixels), alpha and gray channels
for use_alpha, use_gray in [(True,False),(True,True),(False,True)]:
    # use_alpha: use alpha as A, gray as B
    y,x = np.where(a<255)
    A = a[y,x].astype(np.float64); B = g[y,x].astype(np.float64)
    for tA,tB,ph in [(167,245,144),(167,245,106),(292,106,144),(167,245,212),(245,167,144)]:
        I = np.cos((ph + tA*A + tB*B)/2.0)**2
        for inv in [0,1]:
            kb = ((I>=0.5).astype(np.uint8) ^ inv).astype(np.uint8)
            if len(kb)==32 and oracle(kb):
                print("PHOTO_COS2 alpha=%s gray=%s tA=%s tB=%s ph=%s inv=%s HIT" % (use_alpha,use_gray,tA,tB,ph,inv))
# E2: gate params grid (thetaA,thetaB,phi0) over alpha/gray
print("E2 start")
for tA in [167,245,144,212,292,106,250,220,137,208,144,226]:
    for tB in [167,245,144,212,292,106,250,220,137,208,144,226]:
        for phi0 in [167,245,144,212,292,106,250,220,137,208,144,226]:
            for inv in [0,1]:
                I = np.cos((phi0 + tA*al + tB*gr)/2.0)**2
                kb = ((I>=0.5).astype(np.uint8) ^ inv).astype(np.uint8)
                if len(kb)==32 and oracle(kb):
                    print("GATE_HIT tA=%s tB=%s phi0=%s inv=%s" % (tA,tB,phi0,inv))
print("E2 done")
