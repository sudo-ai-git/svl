#!/usr/bin/env python3
"""Run every SVL improvement spike and print a verdict table."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPIKES = sorted(d for d in os.listdir(HERE)
                if os.path.isdir(os.path.join(HERE, d)) and d[:1].isdigit())

rows = []
for name in SPIKES:
    script = os.path.join(HERE, name, "spike.py")
    if not os.path.exists(script):
        continue
    p = subprocess.run([sys.executable, script], capture_output=True, text=True,
                       cwd=HERE, timeout=300)
    out = (p.stdout or "").strip().splitlines()
    line = out[-1] if out else f"(no output; exit {p.returncode})"
    verdict = "VALIDATED" if "VALIDATED" in line else ("INVALIDATED" if "INVALIDATED" in line else "?")
    rows.append((name, verdict, line))

print("=" * 100)
print("SVL IMPROVEMENT SPIKE SUITE")
print("=" * 100)
for name, verdict, line in rows:
    print(f"{name:<40} {verdict:<12} {line[:80]}")
print("-" * 100)
nv = sum(1 for _, v, _ in rows if v == "VALIDATED")
ni = sum(1 for _, v, _ in rows if v == "INVALIDATED")
print(f"TOTAL {len(rows)} | VALIDATED {nv} | INVALIDATED {ni}")
