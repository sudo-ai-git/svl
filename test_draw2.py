from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

# The last session's findings:
# 1. 434 non-255 alpha pixels forming 55 components
# 2. Component 48/35 is the marker (largest, 38px, at (21,791))
# 3. Capacity: 165 bytes > 32-byte key
# 4. All encodings tested negative

# The next step: test the DRAWING content (gray channel) as a data channel
# The gray channel has: buildings, sailboat, water (gray=0), hatching (248-254)

# Test 1: The gray=0 pixels (101K) as a data channel
print("=== Testing gray=0 pixels ===")
gray0_mask = (gray == 0)
ys, xs = np.where(gray0_mask)
print(f"gray=0 pixels: {len(ys)}")

# Pack gray=0 pixel x-coordinates as data
n = len(ys)
nbytes = (n + 7) // 8
raw = bytearray(nbytes)
for i in range(n):
    byte_idx = i // 8
    bit = i % 8
    if gray0_mask[ys[i], xs[i]]:
        raw[byte_idx] |= (1 << (7 - bit))

# Check for target
found = False
for start in range(len(raw) - 32 + 1):
    if raw[start:start+32] == TARGET:
        print(f"TARGET FOUND (gray=0 x) at offset {start}")
        found = True
        break
if not found:
    print(f"gray=0 x: {len(raw)} bytes, no target")

# Test 2: The gray=0 pixel y-coordinates
nbytes = (n + 7) // 8
raw = bytearray(nbytes)
for i in range(n):
    byte_idx = i // 8
    bit = i % 8
    if gray0_mask[ys[i], xs[i]]:
        raw[byte_idx] |= (1 << (7 - bit))

found = False
for start in range(len(raw) - 32 + 1):
    if raw[start:start+32] == TARGET:
        print(f"TARGET FOUND (gray=0 y) at offset {start}")
        found = True
        break
if not found:
    print(f"gray=0 y: {len(raw)} bytes, no target")

# Test 3: The hatch pattern (248-254) as a data channel
print("\n=== Testing hatch pattern ===")
hatch_mask = (gray >= 248) & (gray <= 254)
ys, xs = np.where(hatch_mask)
print(f"hatch pixels: {len(ys)}")

nbytes = (len(ys) + 7) // 8
raw = bytearray(nbytes)
for i in range(len(ys)):
    byte_idx = i // 8
    bit = i % 8
    if hatch_mask[ys[i], xs[i]]:
        raw[byte_idx] |= (1 << (7 - bit))

found = False
for start in range(len(raw) - 32 + 1):
    if raw[start:start+32] == TARGET:
        print(f"TARGET FOUND (hatch x) at offset {start}")
        found = True
        break
if not found:
    print(f"hatch x: {len(raw)} bytes, no target")
