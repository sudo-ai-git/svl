from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

# Get the alpha<255 pixels (the stroke path)
mask = (alpha < 255)
ys, xs = np.where(mask)

# Find connected components
struct = np.array([[0,1,0],[1,1,1],[0,1,0]])
lab, n = ndimage.label(mask, structure=struct)

# Get all stroke segments (run-length encoded strokes)
# The strokes are the individual line segments between gaps
# Let's extract the stroke path as a sequence of (x,y) points

# For each component, get the pixel points
components = []
for i in range(1, n+1):
    comp_mask = (lab == i)
    comp_ys, comp_xs = np.where(comp_mask)
    if len(comp_ys) > 0:
        components.append((i, comp_ys, comp_xs))

# Sort components by raster order (y, then x) using centroid
centroids = []
for i, cy, cx in components:
    cy_mean = np.mean(cy)
    cx_mean = np.mean(cx)
    centroids.append((cy_mean, cx_mean, i, cy, cx))

centroids.sort(key=lambda t: (t[0], t[1]))

print(f"Total components: {len(centroids)}")

# Extract stroke lengths from each component
stroke_lengths = []
for cy_mean, cx_mean, i, cy, cx in centroids:
    # Get the bounding box of the component
    y_min, y_max = cy.min(), cy.max()
    x_min, x_max = cx.min(), cx.max()
    
    # Try to extract the stroke path (using topmost row scan)
    stroke_pts = []
    for y in range(y_min, y_max + 1):
        row_mask = comp_mask[y]
        xs_row = np.where(row_mask)[0]
        if len(xs_row) > 0:
            stroke_pts.append((y, xs_row[0], xs_row[-1]))
    
    # Calculate the merged length of the stroke
    if len(stroke_pts) > 1:
        total_len = 0
        for j in range(1, len(stroke_pts)):
            y1, x1a, x1b = stroke_pts[j-1]
            y2, x2a, x2b = stroke_pts[j]
            # Approximate length as vertical + horizontal distance
            vert = abs(y2 - y1)
            horiz = max(x1b - x1a, x2b - x2a)
            total_len += np.sqrt(vert**2 + horiz**2)
        stroke_lengths.append((total_len, i, cy_mean))
    else:
        # Single row, length = number of pixels
        stroke_lengths.append((len(stroke_pts), i, cy_mean))

stroke_lengths.sort(key=lambda t: t[2])  # Sort by y

print(f"Total strokes: {len(stroke_lengths)}")
print("Stroke lengths (in order):")
for length, i, cy_mean in stroke_lengths:
    print(f"  Component {i}: length={length:.1f}px, y={cy_mean:.1f}")

# Now extract gaps between strokes
# The gaps are the vertical distances between consecutive strokes
gap_lengths = []
for j in range(1, len(stroke_lengths)):
    len1, i1, cy1_mean = stroke_lengths[j-1]
    len2, i2, cy2_mean = stroke_lengths[j]
    gap = cy2_mean - cy1_mean
    gap_lengths.append(gap)

print(f"\nTotal gaps: {len(gap_lengths)}")
print("Gap lengths (in order):")
for g in gap_lengths:
    print(f"  {g:.1f}px")

# Visualize the gap distribution
import collections
gap_bins = collections.Counter()
for g in gap_lengths:
    if g < 12:
        gap_bins['short(<12)'] += 1
    elif g < 60:
        gap_bins['medium(12-60)'] += 1
    else:
        gap_bins['long(>60)'] += 1
print(f"\nGap distribution: {dict(gap_bins)}")
