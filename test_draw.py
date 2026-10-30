from PIL import Image
import numpy as np

img = Image.open('pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)

# The last session said: "gray IDENTICAL; alpha is pure overlay"
# So the gray channel is the ORIGINAL drawing
# Let's investigate the gray channel as a data channel

# The gray channel has:
# - 101,346 pixels with value 0 (darkest - water, shadows)
# - 28,305 pixels with values 248-254 (hatching - diagonal lines)
# - 1,248,522 pixels with value 255 (white - sky)

# The draw (gray < 255) has 101,346 + 28,305 + 23,802 = 153,453 pixels
draw_mask = (gray < 255)
print(f"Draw pixels (gray < 255): {draw_mask.sum()}")

# Extract the draw pixels
ys, xs = np.where(draw_mask)
draw_vals = gray[draw_mask]
print(f"Draw pixels: {len(ys)}")
print(f"Draw value distribution: {np.bincount(draw_vals, minlength=256)[:10]}")

# Test: pack draw pixel x-coordinates as data
# Each x is 0-1599 (11 bits)
print("\n=== Testing draw pixel x-coordinates ===")
bits = []
for i in range(len(xs)):
    x = xs[i]
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
# Check first few bytes
print(f"First 32 bytes: {raw[:32].hex()}")
PY