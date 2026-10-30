#!/usr/bin/env python3
"""Parallel driver for the C fast_oracle. Splits candidates across N processes."""
import os, subprocess, sys, math

CT = '/home/sudosudo/.openclaw/workspace/encrypted_msg.txt'
BIN = '/home/sudosudo/.openclaw/workspace/fast_oracle'
BASE = '/home/sudosudo/.openclaw/workspace/_pc'

def run(cands, workers=8, label="sweep", quiet=False):
    cands = [c for c in cands if c]
    n = len(cands)
    if n == 0:
        print(f"[{label}] no candidates"); return []
    chunk = math.ceil(n / workers)
    procs, parts = [], []
    for w in range(workers):
        pf = f'{BASE}_{w}.txt'; parts.append(pf)
        with open(pf, 'w') as f:
            f.write('\n'.join(cands[w*chunk:(w+1)*chunk]))
        procs.append(subprocess.Popen([BIN, CT, pf], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True))
    matches = []
    for p in procs:
        out, _ = p.communicate()
        for line in out.splitlines():
            if line.startswith('MATCH: '):
                matches.append(line[7:])
    for pf in parts:
        try: os.remove(pf)
        except OSError: pass
    if not quiet or matches:
        print(f"[{label}] tested {n} candidates, {len(matches)} matches")
    for m in matches:
        print("  *** MATCH:", m)
    return matches

if __name__ == '__main__':
    cands = [l.rstrip('\n') for l in sys.stdin]
    run(cands)
