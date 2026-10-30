from PIL import Image
import numpy as np

img = Image.open('/home/sudosudo/.openclaw/workspace/puzzle10_main.png').convert('RGB')
a = np.array(img)
print("shape:", a.shape)

# Background appears to be (0,175,228) cyan based on corners
bg = np.array([0,175,228])
diff = np.abs(a.astype(int) - bg).sum(axis=2)
mask = diff > 60  # non-background
print("non-bg pixels:", mask.sum(), "of", mask.size, f"({100*mask.sum()/mask.size:.1f}%)")

# Find bounding box of non-bg content
ys, xs = np.where(mask)
print("content bbox: x", xs.min(), xs.max(), " y", ys.min(), ys.max())

# Row profile - find bands of content (the torn paper pieces)
rowsum = mask.sum(axis=1)
colsum = mask.sum(axis=0)
print("\nRow profile (every 20px):")
for i in range(0, a.shape[0], 20):
    bar = '#' * int(rowsum[i] / 20)
    print(f"  y={i:4d} {rowsum[i]:5d} {bar}")
print("\nCol profile (every 30px):")
for i in range(0, a.shape[1], 30):
    bar = '#' * int(colsum[i] / 20)
    print(f"  x={i:4d} {colsum[i]:5d} {bar}")
