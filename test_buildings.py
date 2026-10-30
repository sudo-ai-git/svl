from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

# The last session's geom_sweep measured 12 buildings
# Let's expand: measure ALL building-like components in the gray channel

# Find gray=255 components (sky + buildings)
sky_mask = (gray == 255)
lab, n_sky = ndimage.label(sky_mask)
sizes = ndimage.sum(sky_mask, lab, range(1, n_sky+1))

# The buildings are large components in the top half (y < 600)
# Let's measure them more carefully
top_half_components = []
for i in range(n_sky):
    comp_mask = (lab == i+1)
    ys, xs = np.where(comp_mask)
    if len(ys) > 100:  # large components
        cy = ys.mean()
        cx = xs.mean()
        if cy < 600:
            top_half_components.append((sizes[i], cx, cy, i+1))

top_half_components.sort(key=lambda x: -x[2])  # sort by y (topmost first)

print(f"Large top-half components: {len(top_half_components)}")

# Extract building geometry
print("\n=== Building geometry (expanded) ===")
buildings = []
for size, cx, cy, comp_id in top_half_components[:15]:
    # Get the actual building pixels
    comp_mask = (lab == comp_id)
    ys, xs = np.where(comp_mask)
    # Compute building height (min y to max y)
    h = ys.max() - ys.min()
    w = xs.max() - xs.min()
    buildings.append((comp_id, size, cx, cy, h, w))

for comp_id, size, cx, cy, h, w in buildings:
    print(f"  comp {comp_id}: size={size:.0f}, pos=({cx:.1f},{cy:.1f}), h={h}, w={w}")
