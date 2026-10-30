from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

# Get all 434 alpha<255 pixels in raster order
ys, xs = np.where(alpha < 255)
idx = np.lexsort((xs, ys))
av = alpha[ys[idx], xs[idx]].astype(np.uint8)

print(f"Total alpha<255 pixels: {len(av)}")
print(f"Alpha values (raster order): {av.tolist()}")

# TEST 1: Alpha values as 5-bit symbols, packed directly (not bit-by-bit)
# 434 values * 5 bits = 2170 bits = 271.25 bytes
print("\n=== TEST 1: Alpha values as 5-bit symbols (raster order) ===")
bits = []
for a in av:
    for bit in range(5):
        bits.append((a >> bit) & 1)
nbytes = (len(bits) + 7) // 8
raw = bytearray(nbytes)
for i, bit in enumerate(bits):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw[byte_idx] |= (1 << (7 - bit_in_byte))

print(f"Raw bytes: {len(raw)}")
print(f"First 64 bytes: {raw[:64].hex()}")

found = False
for start in range(len(raw) - 32 + 1):
    if raw[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found = True
        break
if not found:
    print("No target found in alpha 5-bit raster order")

# TEST 2: Alpha values as bytes directly (the values themselves, 0-255)
print("\n=== TEST 2: Alpha values as raw bytes (raster order) ===")
raw2 = av.tobytes()
print(f"Raw bytes: {len(raw2)}")
print(f"First 64 bytes: {raw2[:64].hex()}")

found2 = False
for start in range(len(raw2) - 32 + 1):
    if raw2[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found2 = True
        break
if not found2:
    print("No target found in alpha raw bytes")

# TEST 3: Column-major order (transpose)
print("\n=== TEST 3: Alpha values in column-major order ===")
av_t = alpha.T.flatten()
# Get only alpha<255 in column-major order
mask = alpha < 255
ys_t, xs_t = np.where(mask)
idx_t = np.lexsort((ys_t, xs_t))
av_tm = alpha[ys_t[idx_t], xs_t[idx_t]].astype(np.uint8)
bits_t = []
for a in av_tm:
    for bit in range(5):
        bits_t.append((a >> bit) & 1)
nbytes_t = (len(bits_t) + 7) // 8
raw_t = bytearray(nbytes_t)
for i, bit in enumerate(bits_t):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw_t[byte_idx] |= (1 << (7 - bit_in_byte))

found3 = False
for start in range(len(raw_t) - 32 + 1):
    if raw_t[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found3 = True
        break
if not found3:
    print("No target found in alpha column-major 5-bit")

# TEST 4: Gray values at component centroids (as bytes)
print("\n=== TEST 4: Gray values at component centroids ===")
mask = (alpha < 255)
struct = np.array([[0,1,0],[1,1,1],[0,1,0]])
lab, n = ndimage.label(mask, structure=struct)
sizes = ndimage.sum(mask, lab, range(1, n+1))
com = ndimage.center_of_mass(mask, lab, range(1, n+1))
gray_at_com = []
for i in range(n):
    y, x = int(com[i][0]), int(com[i][1])
    gray_at_com.append(gray[y, x])
print(f"Gray at centroids: {gray_at_com}")

# Pack as bytes
raw4 = bytearray()
for g in gray_at_com:
    raw4.append(g)
print(f"Gray at centroids bytes: {len(raw4)}")
print(f"First 64: {bytes(raw4[:64]).hex()}")

found4 = False
for start in range(len(raw4) - 32 + 1):
    if raw4[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found4 = True
        break
if not found4:
    print("No target found in gray at centroids")

# TEST 5: Alpha values at component centroids (as bytes)
print("\n=== TEST 5: Alpha values at component centroids ===")
alpha_at_com = []
for i in range(n):
    y, x = int(com[i][0]), int(com[i][1])
    alpha_at_com.append(alpha[y, x])
print(f"Alpha at centroids: {alpha_at_com}")

raw5 = bytearray(alpha_at_com)
print(f"Alpha at centroids bytes: {len(raw5)}")
print(f"First 64: {bytes(raw5[:64]).hex()}")

found5 = False
for start in range(len(raw5) - 32 + 1):
    if raw5[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found5 = True
        break
if not found5:
    print("No target found in alpha at centroids")

# TEST 6: Component sizes as data
print("\n=== TEST 6: Component sizes as data ===")
sizes_list = [int(s) for s in sizes]
print(f"Component sizes: {sizes_list}")
# Pack sizes as bytes (mod 256)
raw6 = bytearray(s % 256 for s in sizes_list)
print(f"Component sizes bytes: {len(raw6)}")
print(f"First 64: {bytes(raw6[:64]).hex()}")

found6 = False
for start in range(len(raw6) - 32 + 1):
    if raw6[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found6 = True
        break
if not found6:
    print("No target found in component sizes")

# TEST 7: Component alpha values as bytes
print("\n=== TEST 7: Component alpha values (centroid) as data ===")
alpha_at_com_bytes = bytearray(alpha_at_com)
print(f"Alpha at centroids bytes: {len(alpha_at_com_bytes)}")
print(f"First 64: {bytes(alpha_at_com_bytes[:64]).hex()}")

found7 = False
for start in range(len(alpha_at_com_bytes) - 32 + 1):
    if alpha_at_com_bytes[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found7 = True
        break
if not found7:
    print("No target found in alpha at centroids")

# SUMMARY
print("\n=== SUMMARY ===")
print(f"Test 1 (5-bit raster): {'FOUND' if found else 'NOT FOUND'}")
print(f"Test 2 (raw alpha bytes): {'FOUND' if found2 else 'NOT FOUND'}")
print(f"Test 3 (col-major 5-bit): {'FOUND' if found3 else 'NOT FOUND'}")
print(f"Test 4 (gray at centroids): {'FOUND' if found4 else 'NOT FOUND'}")
print(f"Test 5 (alpha at centroids): {'FOUND' if found5 else 'NOT FOUND'}")
print(f"Test 6 (component sizes): {'FOUND' if found6 else 'NOT FOUND'}")
print(f"Test 7 (alpha at centroids bytes): {'FOUND' if found7 else 'NOT FOUND'}")
