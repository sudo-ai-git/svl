#!/usr/bin/env python3
"""Parallel oracle driver: split a candidate file across N node workers."""
import os, subprocess, sys, math, tempfile

def run_parallel(cands, workers=8, label="sweep"):
    cands = [c for c in cands if c]
    n = len(cands)
    if n == 0:
        print(f"[{label}] no candidates"); return []
    # write cands to a temp file, split by line ranges
    base = '/home/sudosudo/.openclaw/workspace/_sweep'
    full = base + '.txt'
    with open(full, 'w') as f:
        f.write('\n'.join(cands))
    chunk = math.ceil(n / workers)
    procs = []
    part_files = []
    for w in range(workers):
        pf = f'{base}_{w}.txt'
        part_files.append(pf)
        with open(pf, 'w') as f:
            f.write('\n'.join(cands[w*chunk:(w+1)*chunk]))
        procs.append(subprocess.Popen(
            ['node', '/home/sudosudo/.openclaw/workspace/oracle_worker.js', pf],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    matches = []
    for w, p in enumerate(procs):
        out, err = p.communicate()
        for line in out.splitlines():
            if line.startswith('MATCH: '):
                matches.append(line[7:])
    print(f"[{label}] tested {n} candidates, {len(matches)} matches")
    for m in matches:
        print("  *** MATCH:", m)
    for pf in part_files:
        try: os.remove(pf)
        except OSError: pass
    return matches

if __name__ == '__main__':
    # read candidates from stdin
    cands = [l.rstrip('\n') for l in sys.stdin]
    run_parallel(cands)
