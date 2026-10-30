from PIL import Image
import numpy as np

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
alpha = arr[:,:,1].astype(np.uint8)
gray = arr[:,:,0].astype(np.uint8)

# Find where non-255 alpha pixels start
alpha_flat = alpha.flatten()
non255_idx = np.where(alpha_flat != 255)[0]
print(f"First 20 non-255 alpha indices: {non255_idx[:20].tolist()}")
print(f"Total non-255 alpha pixels: {len(non255_idx)}")

# Check the spatial positions of the first few non-255 pixels
ys, xs = np.where(alpha != 255)
print(f"\nFirst 10 non-255 pixels (y, x): {(np.column_stack([ys[:10], xs[:10]])).tolist()}")

# Check the alpha values at the landmark indices (they should be 255)
print("\n=== Landmark positions ===")
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    y, x = idx // 1600, idx % 1600
    print(f"  {name} at idx {idx}: y={y}, x={x}, alpha={alpha[y, x]}, gray={gray[y, x]}")

# Check the full alpha channel at landmark positions
print("\n=== Alpha channel at landmark positions (full view) ==="
)
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    y, x = idx // 1600, idx % 1600
    # Show 10x10 region
    y_start = max(0, y-5)
    y_end = min(1105, y+6)
    x_start = max(0, x-5)
    x_end = min(1600, x+6)
    region = alpha[y_start:y_end, x_start:x_end]
    print(f"  {name}: alpha at ({y},{x})={alpha[y,x]}, region min={region.min()}, max={region.max()}")

# Check the alpha values at a few non-255 positions
print("\n=== Alpha values at non-255 positions ==="
)
print(f"  First 20 non-255 alpha values: {alpha_flat[non255_idx[:20]].tolist()}")
print(f"  Last 20 non-255 alpha values: {alpha_flat[non255_idx[-20:]].tolist()}")

# Check the alpha values at the specific landmark indices (with surrounding context)
print("\n=== Alpha values at landmark indices + 20 context each side ==="
)
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    start = max(0, idx - 20)
    end = min(len(alpha_flat), idx + 21)
    context = alpha_flat[start:end]
    print(f"  {name} idx {idx}: {context.tolist()}")

print("\n=== DONE ===")
