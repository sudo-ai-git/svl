from PIL import Image
import numpy as np

img = Image.open('pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)

# Test: hatch pattern as data channel
hatch_mask = (gray >= 248) & (gray <= 254)
ys, xs = np.where(hatch_mask)
print(f"hatch pixels: {len(ys)}")

# Pack hatch x-coordinates as data
n = len(xs)
nbytes = (n + 7) // 8
raw = bytearray(nbytes)
for i in range(n):
    byte_idx = i // 8
    bit = i % 8
    if hatch_mask[ys[i], xs[i]]:
        raw[byte_idx] |= (1 << (7 - bit))

print(f"hatch presence bytes: {len(raw)}")
print(f"First 32 bytes: {raw[:32].hex()}")
