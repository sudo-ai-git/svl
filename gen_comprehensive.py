#!/usr/bin/env python3
"""Comprehensive structured family for PZL10, run with the VALIDATED oracle.
Covers image-order concatenations of the 5 keys' readings, slice-to-20, and
separator variants. (Re-run of a family that was previously tested only with a
broken harness, so those negatives were invalid.)"""
import itertools

# Readings per key (from the puzzle image + README + community research)
K1 = ["124","214","241","142","421","412","12","14","21","24","41","42","1","2","4",
      "148","1248","Dice","dice","HanSolo","Han","Solo","Double","double"]
K2 = ["6318","630","063","63","36","180603","20180603","2018","06","03","0603",
      "Arweave","arweave","ICO","ico","MainSale","Mainsale","Sale","sale","63018","63180"]
K3 = ["66","order66","Order66","executeorder66","ExecuteOrder66","66000000","Sidious",
      "Palpatine","DarthSidious","Darth","Order","order","a","A","66a","a66"]
K4 = ["0","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18","19",
      "01234567890123456789","012345678910111213141516171819","20"]
K5 = ["wellseewhathappens","WellSeeWhatHappens","We'llSeeWhatHappens","WELLSEEWHATHAPPENS",
      "genesis28","Genesis28","genesis","Genesis","28","#28","test","Test"]

cands = set()

# image-order concatenations, 4 keys (k1 k2 k3 k5) then slice to 20; and 5 keys
def add_all(parts, seps=("",)):
    for sep in seps:
        s = sep.join(parts)
        cands.add(s)
        if len(s) >= 20: cands.add(s[:20])
        if len(s) >= 24: cands.add(s[:24])

# 4-key (drop k4 as "length spec"), image order
for a in K1:
    for b in K2:
        for c in K3:
            for e in K5:
                add_all([a,b,c,e])

# 5-key image order (k4 literal)
for a in K1:
    for b in K2:
        for c in K3:
            for d in ["","0-19","[0-19]","01234567890123456789","20"]:
                for e in K5:
                    add_all([a,b,c,d,e])

# k1+k2+k3+k4 (drop k5, image order preserved)
for a in K1:
    for b in K2:
        for c in K3:
            for d in K4:
                add_all([a,b,c,d])

# k1+k2+k3 only (the "4th key = 20 chars" reading)
for a in K1:
    for b in K2:
        for c in K3:
            add_all([a,b,c])

cands = sorted(c for c in cands if c)
with open('/home/sudosudo/.openclaw/workspace/fam_comprehensive.txt','w') as f:
    f.write('\n'.join(cands))
print("generated", len(cands), "candidates")
