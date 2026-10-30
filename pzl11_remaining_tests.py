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

# Get component sizes and centroids
sizes = ndimage.sum(mask, lab, range(1, n+1))
com = ndimage.center_of_mass(mask, lab, range(1, n+1))

# Test 1: Alpha values sorted by component size (ascending)
print("=== TEST 1: Alpha values sorted by component size (ascending) ===")
order = np.argsort(sizes)
alpha_sorted_size = []
for i in order:
    cy, cx = int(com[i][0]), int(com[i][1])
    alpha_sorted_size.append(alpha[cy, cx])
raw1 = bytearray(alpha_sorted_size)
try_bytes(raw1, "alpha at comp centroids (sorted by size)")

# Test 2: Alpha values sorted by component size (descending)
print("\n=== TEST 2: Alpha values sorted by component size (descending) ===")
order_desc = np.argsort(sizes)[::-1]
alpha_sorted_size_desc = []
for i in order_desc:
    cy, cx = int(com[i][0]), int(com[i][1])
    alpha_sorted_size_desc.append(alpha[cy, cx])
raw2 = bytearray(alpha_sorted_size_desc)
try_bytes(raw2, "alpha at comp centroids (sorted by size desc)")

# Test 3: Alpha values sorted by position (column-major order)
print("\n=== TEST 3: Alpha values in column-major order (raster) ===")
ys_cm, xs_cm = np.where(mask)
idx_cm = np.lexsort((ys_cm, xs_cm))
av_cm = alpha[ys_cm[idx_cm], xs_cm[idx_cm]].astype(np.uint8)
raw3 = av_cm.tobytes()
try_bytes(raw3, "alpha in column-major (raster)")

# Test 4: Alpha values in row-major order (x-major)
print("\n=== TEST 4: Alpha values in row-major order (x-first) ===")
idx_rm = np.lexsort((ys_cm, xs_cm))  # same as col-major, need x-major
idx_xmajor = np.lexsort((xs_cm, ys_cm))
av_xmajor = alpha[ys_cm[idx_xmajor], xs_cm[idx_xmajor]].astype(np.uint8)
raw4 = av_xmajor.tobytes()
try_bytes(raw4, "alpha in row-major (x-first)")

# Test 5: Alpha values as 2D reshaped to 1600x1105 (extract non-255 only)
print("\n=== TEST 5: Alpha values as 2D reshaped (only alpha<255, raster) ==="
)
alpha_2d = alpha.copy()
mask_2d = alpha_2d < 255
alpha_values_2d = alpha_2d[mask_2d]
raw5 = alpha_values_2d.tobytes()
try_bytes(raw5, "alpha values as 2D (raster, alpha<255)")

# Test 6: Alpha channel full 1600x1105 raster (including 255s)
print("\n=== TEST 6: Alpha channel full 1600x1105 raster ==="
)
alpha_flat = alpha.flatten()
raw6 = alpha_flat.tobytes()
try_bytes(raw6, "alpha full raster")

# Test 7: Alpha values converted to 5-bit symbols (not 8-bit)
print("\n=== TEST 7: Alpha values as 5-bit symbols (packed) ==="
)
# Use only bits 0-4 (the varying bits)
bits7 = []
for a in alpha_values_2d:
    for bit in range(5):
        bits7.append((a >> bit) & 1)
nbytes7 = (len(bits7) + 7) // 8
raw7 = bytearray(nbytes7)
for i, bit in enumerate(bits7):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw7[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw7, "alpha as 5-bit symbols (packed)")

# Test 8: Gray values in column-major order
print("\n=== TEST 8: Gray values in column-major order ==="
)
gray_flat = gray.flatten()
gray_col_major = gray.T.flatten()  # column-major
raw8 = gray_col_major.tobytes()
try_bytes(raw8, "gray column-major (full image)")

# Test 9: Alpha values with 255 padding removed, then 5-bit packed
print("\n=== TEST 9: Alpha values (255 skipped) as 5-bit symbols ==="
)
# Get all alpha values, skip 255, pack 5-bit
alpha_vals_no255 = alpha_values_2d[alpha_values_2d != 255]
bits9 = []
for a in alpha_vals_no255:
    for bit in range(5):
        bits9.append((a >> bit) & 1)
nbytes9 = (len(bits9) + 7) // 8
raw9 = bytearray(nbytes9)
for i, bit in enumerate(bits9):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw9[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw9, "alpha (no-255) as 5-bit symbols")

print("\n=== ALL TESTS COMPLETE ===")
