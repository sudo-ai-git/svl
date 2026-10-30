#!/usr/bin/env python3
import numpy as np, hashlib, math
from PIL import Image
from eth_account import Account
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
arr = np.array(Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png'))
g = arr[:,:,0].astype(np.uint8).astype(np.float64); a = arr[:,:,1].astype(np.float64)

def oracle(b):
    if len(b)!=32: return False
    try: return Account.from_key(b).address.lower()==PRIZE.lower()
    except: return False

# E1: photo_cos2 over the whole image (alpha & gray), gate params = min-entropy maxp values
# row0 maxp=0.30, sail_alpha maxp=0.445, whole_gray maxp=0.706
for tA,tB,ph in [(0.445,0.30,0.45),(0.706,0.445,0.45),(0.30,0.706,0.45)]:
    for inv in [0,1]:
        for chA in [a,g]:
            for chB in [a,g]:
                I = np.cos((ph + tA*chA + tB*chB)/2.0)**2
                kb = ((I>=0.5).astype(np.uint8) ^ inv).astype(np.uint8)
                if len(kb)==32 and oracle(kb):
                    print("PHOTO_COS2 MAXP tA=%s tB=%s ph=%s inv=%s HIT" % (tA,tB,ph,inv))
print("E1 done")
# E2: cos2 applied to alpha/gray raw values (no gate params), whole image
E2_vals = (a/255.0)**2 + (g/255.0)**2
print("E2 done")

