#!/usr/bin/env python3
"""Spike 018: replace the degenerate PRODUCT channel with a rolling hash (L2)."""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402
from svl.gate231 import product_checksum                       # noqa: E402


def rolling_checksum(data: bytes, modulus: int = 231) -> int:
    """H = (H*31 + b) mod 231 — 31 is coprime to 231, so no byte forces a zero."""
    h = 0
    for b in data:
        h = (h * 31 + b) % modulus
    return h


def main():
    try:
        rng = random.Random(7)
        windows = [bytes(rng.randrange(256) for _ in range(512)) for _ in range(2000)]
        old = [product_checksum(w) for w in windows]
        new = [rolling_checksum(w) for w in windows]
        old_distinct = len(set(old))
        new_distinct = len(set(new))
        new_zeros = sum(1 for v in new if v == 0)
        # a one-byte flip must change the checksum
        w = bytearray(windows[0])
        before = rolling_checksum(bytes(w))
        w[10] ^= 0x01
        after = rolling_checksum(bytes(w))
        flips = (before != after)
        ok = (new_distinct > 100 and new_zeros / 2000 < 0.01 and flips)
        return verdict("018-fix-product-channel", ok,
                       f"old distinct={old_distinct}/2000 (degenerate); "
                       f"new distinct={new_distinct}/2000, zeros={new_zeros}, flip changes={flips}")
    except Exception as exc:
        return verdict("018-fix-product-channel", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
