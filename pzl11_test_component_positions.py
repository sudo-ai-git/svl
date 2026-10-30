from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

# Get all 434 alpha<255 pixels
ys, xs = np.where(alpha < 255)
idx = np.lexsort((xs, ys))
av = alpha[ys[idx], xs[idx]].astype(np.uint8)
xpos = xs[idx]
ypos = ys[idx]

print(f"Total alpha<255 pixels: {len(av)}")

# TEST 1: Component positions (x,y as bytes)
print("\n=== TEST 1: Component positions (x,y as data) ===")
mask = (alpha < 255)
struct = np.array([[0,1,0],[1,1,1],[0,1,0]])
lab, n = ndimage.label(mask, structure=struct)
sizes = ndimage.sum(mask, lab, range(1, n+1))
com = ndimage.center_of_mass(mask, lab, range(1, n+1))

# Pack component x,y as 2 bytes each
raw1 = bytearray()
for i in range(n):
    raw1.append(int(com[i][1]) & 0xFF)  # x
    raw1.append(int(com[i][0]) & 0xFF)  # y
print(f"Component positions bytes: {len(raw1)}")
print(f"First 64: {bytes(raw1[:64]).hex()}")

found = False
for start in range(len(raw1) - 32 + 1):
    if raw1[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found = True
        break
if not found:
    print("Not found in comp positions")

# TEST 2: Alpha values as 2D coordinate system (x = value, y = position)
print("\n=== TEST 2: Alpha values as 2D coordinate system ===")
raw2 = bytearray()
for i, a in enumerate(av):
    raw2.append(a & 0xFF)
    raw2.append(i & 0xFF)
print(f"Alpha as 2D coord bytes: {len(raw2)}")
print(f"First 64: {bytes(raw2[:64]).hex()}")

found2 = False
for start in range(len(raw2) - 32 + 1):
    if raw2[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found2 = True
        break
if not found2:
    print("Not found in alpha 2D coord")

# TEST 3: Gray values as 2D coordinate system (x = gray, y = position)
print("\n=== TEST 3: Gray as 2D coordinate system ===")
gray0_mask = (gray == 0)
ys0, xs0 = np.where(gray0_mask)
gv = gray[ys0, xs0].astype(np.uint8)
print(f"Gray=0 pixels: {len(gv)}")

raw3 = bytearray()
for i, g in enumerate(gv):
    raw3.append(g & 0xFF)
    raw3.append(i & 0xFF)
print(f"Gray as 2D coord bytes: {len(raw3)}")
print(f"First 64: {bytes(raw3[:64]).hex()}")

found3 = False
for start in range(len(raw3) - 32 + 1):
    if raw3[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found3 = True
        break
if not found3:
    print("Not found in gray 2D coord")

# TEST 4: Component sizes as 2-byte values (not 1-byte)
print("\n=== TEST 4: Component sizes as 2-byte values ===")
raw4 = bytearray()
for s in sizes:
    raw4.append((int(s) >> 8) & 0xFF)
    raw4.append(int(s) & 0xFF)
print(f"Component sizes (2-byte) bytes: {len(raw4)}")
print(f"First 64: {bytes(raw4[:64]).hex()}")

found4 = False
for start in range(len(raw4) - 32 + 1):
    if raw4[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found4 = True
        break
if not found4:
    print("Not found in comp sizes 2-byte")

# TEST 5: Alpha values in raster order, but as 8-bit (not 5-bit)
print("\n=== TEST 5: Alpha values as 8-bit bytes (full 256 range) ===")
raw5 = av.tobytes()
print(f"Alpha full bytes: {len(raw5)}")
print(f"First 64: {raw5[:64].hex()}")

found5 = False
for start in range(len(raw5) - 32 + 1):
    if raw5[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found5 = True
        break
if not found5:
    print("Not found in alpha full 8-bit")

# TEST 6: Gray channel full 8-bit raster
print("\n=== TEST 6: Gray channel full 8-bit raster ===")
gray_flat = gray.flatten()
raw6 = gray_flat.tobytes()
print(f"Gray full bytes: {len(raw6)}")
print(f"First 64: {raw6[:64].hex()}")

found6 = False
for start in range(len(raw6) - 32 + 1):
    if raw6[start:start+32] == TARGET:
        print(f"TARGET FOUND at offset {start}")
        found6 = True
        break
if not found6:
    print("Not found in gray full 8-bit")

# SUMMARY
print("\n=== SUMMARY ===")
print(f"Test 1 (comp positions): {'FOUND' if found else 'NOT FOUND'}")
print(f"Test 2 (alpha 2D coord): {'FOUND' if found2 else 'NOT FOUND'}")
print(f"Test 3 (gray 2D coord): {'FOUND' if found3 else 'NOT FOUND'}")
print(f"Test 4 (comp sizes 2-byte): {'FOUND' if found4 else 'NOT FOUND'}")
print(f"Test 5 (alpha full 8-bit): {'FOUND' if found5 else 'NOT FOUND'}")
print(f"Test 6 (gray full 8-bit): {'FOUND' if found6 else 'NOT FOUND'}")
