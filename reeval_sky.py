#!/usr/bin/env python3
"""Re-measure the 12 building heights from the skyline precisely."""
import numpy as np
from PIL import Image
arr = np.array(Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png'))
g = arr[:,:,0].astype(np.uint8); a = arr[:,:,1].astype(np.uint8)
# sail mask: alpha<255
mask = a < 255
ys, xs = np.where(mask)
# all sail pixels
print("sail count:", len(ys))
# y within sail: 378-1102 (groups) and the building region.
# Find the skyline profile by projecting alpha over x... use distinct x ranges per building.
# Approach: row-0 signature curve (at row 0) is the skyline tops.
rows = 1600
for y in range(0, 1200):
    r = mask[y]
    if r.sum() > 400:
        print("row", y, "count", r.sum())
