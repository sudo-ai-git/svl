from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl10_authoritative.png').convert('RGB')
a = np.array(img)
bg = np.array([85,76,76])
diff = np.abs(a.astype(int) - bg).sum(axis=2)
mask = diff > 60

# The image is torn paper pieces on a gray background.
# Find connected components of the "paper" (light regions)
# Paper is white-ish; let's detect bright regions
bright = (a.astype(int).sum(axis=2) > 400)
print("bright pixels:", bright.sum())

# Label bright regions
lbl, n = ndimage.label(bright)
print("bright components:", n)
sizes = ndimage.sum(bright, lbl, range(1, n+1))
# Top components by size
order = np.argsort(sizes)[::-1]
for i in order[:15]:
    comp = i+1
    ys, xs = np.where(lbl==comp)
    print(f"  comp {comp}: size={int(sizes[i])}, bbox x[{xs.min()}-{xs.max()}] y[{ys.min()}-{ys.max()}], center=({int(xs.mean())},{int(ys.mean())})")
