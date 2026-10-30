#!/usr/bin/env python3
"""Open-lead #3 (row-0 de-interpolation) from the PZL11 notes.

The notes: "Row-0 curve as a smoothed signal to de-interpolate to 32 bytes."

The row-0 watermark is a 147-value smooth curve (cols 1013-1400). Approach:
smooth the 147 values (moving-average), then spline-interpolate to 32
sample points -> 32 bytes. Also test the raw 32-point uniform sample, the
curve's slope (derivative), and a smoothed window.

Each 32-byte candidate that is a valid secp256k1 private key is gated through
the oracle (address == 0xff2142e98e09b5344994f9beb9c56c95506b9f17).
"""

import numpy as np
import hashlib
from PIL import Image
from scipy.interpolate import make_interp_spline
from scipy.ndimage import uniform_filter1d
from eth_account import Account

IMG = '/home/sudosudo/.openclaw/workspace/pzl11.png'
PRIZE = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')
# secp256k1 order; a valid private key is in [1, N-1]
N_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140


def load_row0():
    arr = np.array(Image.open(IMG))
    g = arr[:, :, 0].astype(np.uint8)
    r0 = g[0]
    nz = np.where(r0 != 255)[0]
    return g[0, nz].astype(np.float64), nz.astype(np.float64)


def deinterpolate_32(x, y):
    """Smooth y (147 points) then spline-interpolate to 32 sample points."""
    y = uniform_filter1d(y, size=5, origin=-2)
    y = np.clip(y, 0, 255)
    xs = np.linspace(0, len(y) - 1, 32)
    spl = make_interp_spline(np.arange(len(y)), y, k=3)
    yi = spl(xs)
    return np.clip(yi, 0, 255).astype(np.uint8)


def oracle_gate(label, key_bytes):
    """Run the oracle gate only on 32-byte secp256k1-valid keys."""
    if len(key_bytes) != 32:
        return
    key_bytes = np.ascontiguousarray(key_bytes).astype(np.uint8).tobytes()
    ck = int.from_bytes(key_bytes, 'big')
    if ck <= 0 or ck >= N_ORDER:
        return
    for tname, d in [("first32", key_bytes),
                     ("last32", key_bytes),
                     ("rev", key_bytes[::-1])]:
        if Account.from_key(d).address.lower() == PRIZE.lower():
            print("HITCH", label, tname, key_bytes.hex(), PRIZE.hex())


def run():
    x, y = load_row0()
    print("row0 count:", len(y), "cols", x.min(), x.max(),
          "vals range", y.min(), y.max())
    # plain uniform sample of 32
    idx = np.linspace(0, len(y) - 1, 32).astype(int)
    oracle_gate("row0_plain32", y[idx].astype(np.uint8))
    # smooth + spline-interpolate to 32
    yi = deinterpolate_32(x, y)
    oracle_gate("row0_smooth32", yi)
    # curve slope (gradient) -> 32 bytes
    dy = np.gradient(y)
    dyi = np.clip(np.interp(np.linspace(0, len(y) - 1, 32),
                            np.arange(len(y)), dy), 0, 255).astype(np.uint8)
    oracle_gate("row0_slope32", dyi)
    # smoothed values, 32-point window
    ys = uniform_filter1d(y, size=7, origin=-3)
    w32 = np.linspace(0, len(y) - 1, 32).astype(int)
    oracle_gate("row0_smooth_w32", ys[w32].astype(np.uint8))


if __name__ == '__main__':
    run()
