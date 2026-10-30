from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

def try_bytes(raw, name):
    if len(raw) < 32:
        print(f"{name}: too short ({len(raw)} bytes)")
        return False
    found = False
    for start in range(len(raw) - 32 + 1):
        if raw[start:start+32] == TARGET:
            print(f"TARGET FOUND at offset {start} in {name}")
            return True
    print(f"{name}: NOT FOUND ({len(raw)} bytes)")
    return False

# Get all alpha<255 pixels
mask = (alpha < 255)
struct = np.array([[0,1,0],[1,1,1],[0,1,0]])
lab, n = ndimage.label(mask, structure=struct)

# For each component, get all gray values at its pixels
print("=== TEST 1: Gray values at ALL alpha component pixels (1-byte each) ===")
all_gray_vals = []
comp_info = []
for i in range(1, n+1):
    comp_mask = (lab == i)
    comp_gray = gray[comp_mask]
    all_gray_vals.extend(comp_gray.tolist())
    comp_info.append((i, len(comp_gray), comp_gray.min(), comp_gray.max(), comp_gray.mean()))

raw1 = bytearray(all_gray_vals)
try_bytes(raw1, "gray at all alpha comp pixels (1-byte)")

# Test 2: Alpha values at ALL alpha component pixels (1-byte each)
print("\n=== TEST 2: Alpha values at ALL alpha component pixels (1-byte) ===")
all_alpha_vals = []
for i in range(1, n+1):
    comp_mask = (lab == i)
    comp_alpha = alpha[comp_mask]
    all_alpha_vals.extend(comp_alpha.tolist())

raw2 = bytearray(all_alpha_vals)
try_bytes(raw2, "alpha at all alpha comp pixels (1-byte)")

# Test 3: Gray values at component 48's pixels specifically
print("\n=== TEST 3: Gray values at component 48's pixels ===")
comp48_mask = (lab == 48)
comp48_gray = gray[comp48_mask]
print(f"Comp 48 pixels: {len(comp48_gray)}, gray range: {comp48_gray.min()}-{comp48_gray.max()}")
print(f"Gray values: {sorted(comp48_gray.tolist())}")
raw3 = bytearray(sorted(comp48_gray.tolist()))
try_bytes(raw3, "gray at comp 48's pixels (sorted)")

# Test 4: Alpha values at component 48's pixels (sorted)
print("\n=== TEST 4: Alpha values at comp 48's pixels (sorted) ===")
comp48_alpha = alpha[comp48_mask]
print(f"Alpha values: {sorted(comp48_alpha.tolist())}")
raw4 = bytearray(sorted(comp48_alpha.tolist()))
try_bytes(raw4, "alpha at comp 48's pixels (sorted)")

# Test 5: Alpha values as 5-bit symbols at alpha component pixels
print("\n=== TEST 5: Alpha at alpha comp pixels as 5-bit symbols ===")
bits = []
for a in all_alpha_vals:
    for bit in range(5):
        bits.append((a >> bit) & 1)
nbytes = (len(bits) + 7) // 8
raw5 = bytearray(nbytes)
for i, bit in enumerate(bits):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw5[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw5, "alpha at alpha comp pixels (5-bit)")

# Test 6: Gray values as 5-bit symbols at alpha comp pixels
print("\n=== TEST 6: Gray at alpha comp pixels as 5-bit symbols ===")
bits6 = []
for g in all_gray_vals:
    for bit in range(5):
        bits6.append((g >> bit) & 1)
nbytes6 = (len(bits6) + 7) // 8
raw6 = bytearray(nbytes6)
for i, bit in enumerate(bits6):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw6[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw6, "gray at alpha comp pixels (5-bit)")

# Test 7: Gray values at alpha comp pixels in raster order (not per-component)
print("\n=== TEST 7: Gray values at alpha comp pixels in raster order ===")
ys, xs = np.where(mask)
idx = np.lexsort((xs, ys))
gray_raster = gray[ys[idx], xs[idx]].astype(np.uint8)
raw7 = gray_raster.tobytes()
try_bytes(raw7, "gray at alpha pixels (raster)")

print("\n=== ALL TESTS COMPLETE ===")
