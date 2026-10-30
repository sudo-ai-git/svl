from PIL import Image
import numpy as np

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl10_authoritative.png').convert('RGB')
a = np.array(img)
print("shape:", a.shape)

# Background color from corner
bg = a[0,0].astype(int)
print("bg corner:", bg)
diff = np.abs(a.astype(int) - bg).sum(axis=2)
mask = diff > 60
print("non-bg pixels:", mask.sum(), "of", mask.size, f"({100*mask.sum()/mask.size:.1f}%)")

ys, xs = np.where(mask)
print("content bbox: x", xs.min(), xs.max(), " y", ys.min(), ys.max())

rowsum = mask.sum(axis=1)
colsum = mask.sum(axis=0)
print("\nRow profile (every 20px):")
for i in range(0, a.shape[0], 20):
    print(f"  y={i:4d} {rowsum[i]:5d} {'#'*int(rowsum[i]/30)}")
print("\nCol profile (every 30px):")
for i in range(0, a.shape[1], 30):
    print(f"  x={i:4d} {colsum[i]:5d} {'#'*int(colsum[i]/30)}")

# Save a version where we crop to content for closer inspection
img.crop((xs.min(), ys.min(), xs.max()+1, ys.max()+1)).save('/home/sudosudo/.openclaw/workspace/pzl10_crop.png')
print("\nsaved crop")
