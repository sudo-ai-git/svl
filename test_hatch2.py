from PIL import Image
import numpy as np

img = Image.open('pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)

hatch_mask = (gray >= 248) & (gray <= 254)
ys, xs = np.where(hatch_mask)
print(f"hatch pixels: {len(ys)}")

# Check x distribution
print(f"x range: {xs.min()} to {xs.max()}")
print(f"x mean: {xs.mean():.1f}")
print(f"Fraction with x > 128: {(xs > 128).mean():.2f}")

# Try packing hatch values (248-254) as data
hatch_vals = gray[hatch_mask]
print(f"hatch values: min={hatch_vals.min()}, max={hatch_vals.max()}, unique={np.unique(hatch_vals)}")