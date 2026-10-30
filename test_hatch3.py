from PIL import Image
import numpy as np

img = Image.open('pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)

# The last session said: "gray IDENTICAL; alpha is pure overlay"
# So the gray channel is the original drawing, alpha is the overlay
# The drawing has: buildings (skyline), sailboat, water, hatching

# Let's look at the structure of the drawing
# The "hatching" (248-254) forms diagonal lines
# The gray=0 pixels form the dark areas (water, shadows)

# Test: the "hatching" pattern as a coordinate map
# The hatch lines are at specific positions - maybe they encode a message

hatch_mask = (gray >= 248) & (gray <= 254)
ys, xs = np.where(hatch_mask)
print(f"hatch pixels: {len(ys)}")

# The hatch forms diagonal lines - let's look at the pattern
# Group hatch pixels by row
from collections import defaultdict
row_hatch = defaultdict(list)
for y, x in zip(ys, xs):
    row_hatch[y].append(x)

# Look at the hatch pattern in the top half (sky area, y < 500)
print("\n=== Hatch pattern in top half (y < 500) ===")
for y in range(0, 500, 50):
    if y in row_hatch:
        xs_in_row = row_hatch[y]
        # Find hatch runs
        runs = []
        start = xs_in_row[0]
        prev = xs_in_row[0]
        for x in xs_in_row[1:]:
            if x == prev + 1:
                prev = x
            else:
                runs.append((start, prev))
                start = x
                prev = x
        runs.append((start, prev))
        print(f"y={y}: {len(xs_in_row)} hatch pixels, {len(runs)} runs: {runs[:10]}")