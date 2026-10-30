from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

# The last session's findings
# 1. 434 non-255 alpha pixels forming 55 components
# 2. Component 48/35 is the marker (largest, 38px, at (21,791))
# 3. Capacity: 165 bytes > 32-byte key
# 4. All encodings tested negative

# KEY: The gray=0 pixels (101,346) are the darkest areas
# These might encode information through their positions

print("=== Testing gray=0 pixel positions as data channel ===")
gray0_mask = (gray == 0)
ys, xs = np.where(gray0_mask)
print(f"gray=0 pixels: {len(ys)}")

# For the LAST session's finding: "the alpha channel has 434 non-255 pixels"
# The "deliberate signal" is in the alpha channel, NOT the gray channel
# So let's focus on the alpha channel

# Let's test: the positions of the 434 alpha pixels as a data channel
# Each alpha pixel has a position (x, y) and a value
# The "deliberate signal" might be in the SEQUENCE of alpha pixels

# Sort alpha pixels by position (x, then y)
alpha_pixels = list(zip(ys, xs, alpha[ys, xs]))
alpha_pixels.sort()

print(f"Alpha pixels sorted: {len(alpha_pixels)}")
print(f"First 10: {alpha_pixels[:10]}")

# Test: pack the alpha pixel x-coordinates as data
# Each x is 0-1599, needs 11 bits
bits = []
for y, x, val in alpha_pixels:
    for bit in range(10, -1, -1):
        bits.append((x >> bit) & 1)

nbytes = (len(bits) + 7) // 8
raw = bytearray(nbytes)
for i, bit in enumerate(bits):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw[byte_idx] |= (1 << (7 - bit_in_byte))

print(f"x coords packed: {len(raw)} bytes")
found = False
for start in range(len(raw) - 32 + 1):
    if raw[start:start+32] == TARGET:
        print(f"TARGET FOUND (x coords) at offset {start}")
        found = True
        break
if not found:
    print("x coords: no target")