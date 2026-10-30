from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

# Test hypothesis: the "deliberate signal" is in the relationship between
# the 55 alpha components and the drawing content (gray < 255)

# Create a "content" mask
content_mask = (gray < 255)

# Extract alpha components
mask = (alpha < 255)
lab, n = ndimage.label(mask, structure=np.array([[0,1,0],[1,1,1],[0,1,0]]))
sizes = ndimage.sum(mask, lab, range(1, n+1))
com = ndimage.center_of_mass(mask, lab, range(1, n+1))
cy = np.array([int(c[0]) for c in com])
cx = np.array([int(c[1]) for c in com])

# Test: pack component properties as data
# For each component, encode: on_content (0/1) + size category (0-3)
print("=== Testing component properties encoding ===")

# Size categories:
# 0: size < 5 (tiny)
# 1: 5 <= size < 15 (small)
# 2: 15 <= size < 30 (medium)
# 3: size >= 30 (large)
categories = []
for s in sizes:
    s = int(s)
    if s < 5:
        categories.append(0)
    elif s < 15:
        categories.append(1)
    elif s < 30:
        categories.append(2)
    else:
        categories.append(3)

# Pack as 2 bits per component (category), then 1 bit for on_content
# Total: 3 bits per component
bits = []
for i in range(n):
    bits.append(categories[i] & 3)  # low 2 bits
    bits.append(1 if gray[cy[i], cx[i]] < 255 else 0)  # on content

# Pack into bytes
nbytes = (len(bits) + 7) // 8
raw = bytearray(nbytes)
for i, bit in enumerate(bits):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw[byte_idx] |= (1 << (7 - bit_in_byte))

# Check for target
found = False
for start in range(len(raw) - 32 + 1):
    if raw[start:start+32] == TARGET:
        print(f"TARGET FOUND (props) at offset {start}")
        found = True
        break
if not found:
    print(f"props: {len(raw)} bytes, no target")