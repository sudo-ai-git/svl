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

# 1. Gray values at alpha component positions (centroids)
print("=== TEST 1: Gray at alpha component centroids ===")
mask = (alpha < 255)
struct = np.array([[0,1,0],[1,1,1],[0,1,0]])
lab, n = ndimage.label(mask, structure=struct)
com = ndimage.center_of_mass(mask, lab, range(1, n+1))
gray_at_com = [gray[int(c[0]), int(c[1])] for c in com]
raw1 = bytearray(gray_at_com)
try_bytes(raw1, "gray at alpha comp centroids")

# 2. Alpha values at the gray=0 positions
print("\n=== TEST 2: Alpha at gray=0 positions ===")
gray0_mask = (gray == 0)
ys0, xs0 = np.where(gray0_mask)
# Check alpha at these positions
alpha_at_gray0 = alpha[ys0, xs0]
print(f"Alpha at gray=0 positions: {len(alpha_at_gray0)} values, unique: {np.unique(alpha_at_gray0)[:10]}")
raw2 = alpha_at_gray0.tobytes()
try_bytes(raw2, "alpha at gray=0 positions")

# 3. Gray=0 positions as data (x,y pairs)
print("\n=== TEST 3: Gray=0 positions as data (x,y) ===")
raw3 = bytearray()
for y, x in zip(ys0, xs0):
    raw3.append(x & 0xFF)
    raw3.append(y & 0xFF)
print(f"Gray=0 positions bytes: {len(raw3)}")
try_bytes(raw3, "gray=0 positions (x,y)")

# 4. Building heights as 1-byte values
print("=== TEST 4: Building heights as 1-byte values ===")
B = [(234,322,161,328),(326,412,78,323),(416,500,183,327),(502,676,107,319),
     (678,782,20,312),(884,978,201,307),(980,1140,72,322),(1142,1258,101,321),
     (1260,1348,176,313),(1350,1452,105,313),(1454,1510,163,307),(1514,1592,74,300)]
H = [b[3]-b[2] for b in B]
print(f"Heights: {H}")
# Fix: 292 > 255, take modulo 256
H = [h & 0xFF for h in H]
raw4 = bytearray(H)
try_bytes(raw4, "building heights")

# 5. Building widths as 1-byte values
print("\n=== TEST 5: Building widths as 1-byte values ===")
WID = [b[1]-b[0] for b in B]
raw5 = bytearray(WID)
try_bytes(raw5, "building widths")

# 6. Combined geometry (H,W,H,W,...)
print("\n=== TEST 6: Combined geometry (H,W,H,W,...) ===")
raw6 = bytearray()
for h, w in zip(H, WID):
    raw6.append(h & 0xFF)
    raw6.append(w & 0xFF)
try_bytes(raw6, "combined H,W,H,W")

# 7. Combined geometry (H,W) with 2-byte values
print("\n=== TEST 7: Combined geometry (H,W) as 2-byte LE ===")
raw7 = bytearray()
for h, w in zip(H, WID):
    raw7.append(w & 0xFF)
    raw7.append((w >> 8) & 0xFF)
    raw7.append(h & 0xFF)
    raw7.append((h >> 8) & 0xFF)
try_bytes(raw7, "combined H,W (2-byte LE)")

# 8. Alpha values at gray=0 positions (raw bytes)
print("\n=== TEST 8: Alpha values at gray=0 positions (raw) ===")
raw8 = alpha_at_gray0.tobytes()
try_bytes(raw8, "alpha at gray=0 (raw)")

# 9. Alpha values at gray=0 positions (5-bit symbols)
print("\n=== TEST 9: Alpha values at gray=0 positions (5-bit) ===")
bits = []
for a in alpha_at_gray0:
    for bit in range(5):
        bits.append((a >> bit) & 1)
nbytes = (len(bits) + 7) // 8
raw9 = bytearray(nbytes)
for i, bit in enumerate(bits):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw9[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw9, "alpha at gray=0 (5-bit)")

# 10. Gray=0 pixels as raw bytes
print("\n=== TEST 10: Gray=0 pixels as raw bytes ===")
gv = gray[ys0, xs0].astype(np.uint8)
raw10 = gv.tobytes()
try_bytes(raw10, "gray=0 pixels (raw)")

# 11. Gray=0 pixels as 5-bit symbols
print("\n=== TEST 11: Gray=0 pixels as 5-bit symbols ===")
bits11 = []
for g in gv:
    for bit in range(5):
        bits11.append((g >> bit) & 1)
nbytes11 = (len(bits11) + 7) // 8
raw11 = bytearray(nbytes11)
for i, bit in enumerate(bits11):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw11[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw11, "gray=0 pixels (5-bit)")

# 12. Alpha values sorted by component size (ascending)
print("\n=== TEST 12: Alpha values sorted by component size ===")
sizes = ndimage.sum(mask, lab, range(1, n+1))
com2 = ndimage.center_of_mass(mask, lab, range(1, n+1))
# Sort components by size, then take centroid alpha values
order = np.argsort(sizes)
alpha_sorted = [alpha[int(com[i][0]), int(com[i][1])] for i in order]
raw12 = bytearray(alpha_sorted)
try_bytes(raw12, "alpha at comp centroids (sorted by size)")

# 13. Alpha values in column-major order (raster)
print("\n=== TEST 13: Alpha values in column-major order ===")
ys_cm, xs_cm = np.where(mask)
idx_cm = np.lexsort((ys_cm, xs_cm))
av_cm = alpha[ys_cm[idx_cm], xs_cm[idx_cm]].astype(np.uint8)
raw13 = av_cm.tobytes()
try_bytes(raw13, "alpha in column-major (raster)")

# 14. Alpha values as 2D reshaped (1600x1105) - take only alpha<255
print("\n=== TEST 14: Alpha values as 2D reshaped (only alpha<255) ===")
alpha_2d = alpha.copy()
# Extract non-255 values in image order
mask_2d = alpha_2d < 255
alpha_values_2d = alpha_2d[mask_2d]
raw14 = alpha_values_2d.tobytes()
try_bytes(raw14, "alpha values as 2D (raster, alpha<255)")

# 15. Gray channel full raster (1600x1105)
print("\n=== TEST 15: Gray channel full raster ===")
gray_flat = gray.flatten()
raw15 = gray_flat.tobytes()
try_bytes(raw15, "gray full raster")

# 16. Alpha channel full raster (1600x1105)
print("\n=== TEST 16: Alpha channel full raster ===")
alpha_flat = alpha.flatten()
raw16 = alpha_flat.tobytes()
try_bytes(raw16, "alpha full raster")

# 17. Gray values at gray<128 positions (dark areas)
print("\n=== TEST 17: Gray values at gray<128 positions ===")
dark_mask = (gray < 128)
gv_dark = gray[dark_mask]
raw17 = gv_dark.tobytes()
try_bytes(raw17, "gray<128 pixels (raw)")

# 18. Gray values at gray<128 positions (5-bit)
print("\n=== TEST 18: Gray<128 pixels as 5-bit symbols ===")
bits18 = []
for g in gv_dark:
    for bit in range(5):
        bits18.append((g >> bit) & 1)
nbytes18 = (len(bits18) + 7) // 8
raw18 = bytearray(nbytes18)
for i, bit in enumerate(bits18):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw18[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw18, "gray<128 pixels (5-bit)")

# 19. Alpha values at hatch positions (gray 248-254)
print("\n=== TEST 19: Alpha values at hatch positions (gray 248-254) ===")
hatch_mask = (gray >= 248) & (gray <= 254)
y_hatch, x_hatch = np.where(hatch_mask)
alpha_at_hatch = alpha[y_hatch, x_hatch]
raw19 = alpha_at_hatch.tobytes()
try_bytes(raw19, "alpha at hatch positions (raw)")

# 20. Gray values at hatch positions
print("\n=== TEST 20: Gray values at hatch positions (raw) ===")
gh_hatch = gray[y_hatch, x_hatch].astype(np.uint8)
raw20 = gh_hatch.tobytes()
try_bytes(raw20, "gray at hatch positions (raw)")

print("\n=== ALL TESTS COMPLETE ===")
