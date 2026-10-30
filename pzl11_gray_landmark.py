from PIL import Image
import numpy as np

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

print("=== Gray channel at landmark positions ==="
)
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    y, x = idx // 1600, idx % 1600
    print(f"  {name} at ({y},{x}): gray={gray[y,x]}, alpha={alpha[y,x]}")

# Check if row 0 has any non-255 values in gray or alpha
print("\n=== Row 0 non-255 values (gray and alpha) ==="
)
row0_gray = gray[0, :]
row0_alpha = alpha[0, :]
non255_gray = np.where(row0_gray != 255)[0]
non255_alpha = np.where(row0_alpha != 255)[0]
print(f"  Row 0 gray non-255: {len(non255_gray)}, indices: {non255_gray[:20].tolist()}")
print(f"  Row 0 alpha non-255: {len(non255_alpha)}, indices: {non255_alpha[:20].tolist()}")

# Check rows 1-10
print("\n=== Rows 1-10 non-255 alpha values ==="
)
for r in range(1, 11):
    n = np.sum(alpha[r, :] != 255)
    print(f"  Row {r}: {n} non-255 alpha pixels")

# Find the first rows with non-255 alpha
rows_with_data = np.where(np.any(alpha != 255, axis=1))[0]
print(f"\n  First row with non-255 alpha: {rows_with_data[0]}")
print(f"  Last row with non-255 alpha: {rows_with_data[-1]}")

# Check the gray channel at the first rows with non-255 alpha
y_start = rows_with_data[0]
print(f"\n  Gray channel at rows {y_start}-{y_start+10}:")
for r in range(y_start, y_start+10):
    row = gray[r, :]
    non255 = np.where(row != 255)[0]
    if len(non255) > 0:
        print(f"    Row {r}: gray non-255 count={len(non255)}, min={row[non255].min()}, max={row[non255].max()}")

# Check the alpha channel at the first rows with non-255 alpha
print(f"\n  Alpha channel at rows {y_start}-{y_start+5}:")
for r in range(y_start, y_start+5):
    row = alpha[r, :]
    non255 = np.where(row != 255)[0]
    if len(non255) > 0:
        print(f"    Row {r}: alpha non-255 count={len(non255)}, values={sorted(row[non255].tolist())}")

# Test: the alpha values at indices 11, 43, 154, 314 in the FULL image (gray + alpha)
print("\n=== Full image data at landmark positions ==="
)
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    y, x = idx // 1600, idx % 1600
    print(f"  {name} at ({y},{x}): gray={gray[y,x]}, alpha={alpha[y,x]}")

# Test: Maybe the landmark indices are in the gray channel (not alpha)
# Let me check the first 314 gray values
print("\n=== First 314 gray values ==="
)
gray_flat = gray.flatten()
print(f"  Gray[0:314] first 40: {gray_flat[0:40].tolist()}")
print(f"  Gray[0:314] non-255 count: {np.sum(gray_flat[0:314] != 255)}")

print("\n=== DONE ===")
