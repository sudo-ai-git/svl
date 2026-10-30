from PIL import Image
import numpy as np

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

# Extract row 0's non-255 gray values
row0_gray = gray[0, :]
row0_non255 = row0_gray[row0_gray != 255]
print(f"Row 0 non-255 gray values: {row0_non255.tolist()}")
print(f"Row 0 non-255 count: {len(row0_non255)}")

# Test: the non-255 gray values as bytes
print("\n=== TEST 1: Row 0 non-255 gray values as bytes ==="
)
raw1 = bytearray(row0_non255.tolist())
TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

def try_bytes(raw, name):
    if len(raw) < 32:
        print(f"{name}: too short ({len(raw)} bytes)")
        return
    found = False
    for start in range(len(raw) - 32 + 1):
        if raw[start:start+32] == TARGET:
            print(f"TARGET FOUND at offset {start} in {name}")
            return
    print(f"{name}: NOT FOUND ({len(raw)} bytes)")

try_bytes(raw1, "row 0 non-255 gray values (1-byte)")

# Test: the gray values at indices 1013-1400 (row 0)
print("\n=== TEST 2: Row 0 gray values at indices 1013-1400 ==="
)
block = gray[0, 1013:1400]
print(f"  Block size: {len(block)}, values: {block.tolist()}")
try_bytes(block.tobytes(), "row 0 gray 1013-1400")

# Test: the gray values in row 0 as raw bytes
print("\n=== TEST 3: Row 0 gray values as raw bytes (full row) ==="
)
raw3 = row0_gray.tobytes()
try_bytes(raw3, "row 0 gray full row")

# Test: the alpha values in row 0 (all 255)
print("\n=== TEST 4: Row 0 alpha values ==="
)
row0_alpha = alpha[0, :]
print(f"  Row 0 alpha unique: {np.unique(row0_alpha)}")

# Test: the gray values at the landmark positions (11, 43, 154, 314)
print("\n=== TEST 5: Gray values at landmark positions ==="
)
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    print(f"  {name} at idx {idx}: gray={gray[0, idx]}, alpha={alpha[0, idx]}")

# Test: the alpha values in the region y=378-400 (where the sailboat starts)
print("\n=== TEST 6: Alpha values in y=378-400 (sailboat region) ==="
)
sailboat_alpha = alpha[378:400, :]
print(f"  Sailboat region size: {sailboat_alpha.shape}")
print(f"  Alpha non-255 count: {np.sum(sailboat_alpha != 255)}")

# Test: the alpha values at the landmarks, converted to bytes with surrounding context
print("\n=== TEST 7: Alpha values around landmarks (with context) ==="
)
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    start = max(0, idx - 5)
    end = min(len(alpha.flatten()), idx + 6)
    context = alpha.flatten()[start:end]
    print(f"  {name}: {context.tolist()}")

# Test: the gray values in the building region (y=378-1100)
print("\n=== TEST 8: Gray values in building region (y=378-1100, first 1000 cols) ==="
)
building_gray = gray[378:1100, 0:1000]
print(f"  Building region shape: {building_gray.shape}")
print(f"  Building region min: {building_gray.min()}, max: {building_gray.max()}")
print(f"  Building region non-255 count: {np.sum(building_gray != 255)}")

# Test: the alpha values in the building region (y=378-1100)
print("\n=== TEST 9: Alpha values in building region (y=378-1100) ==="
)
building_alpha = alpha[378:1100, :]
print(f"  Building region non-255 count: {np.sum(building_alpha != 255)}")

# Test: the alpha values at the first non-255 positions (y=378)
print("\n=== TEST 10: Alpha values at y=378 (first data row) ==="
)
row378 = alpha[378, :]
non255_378 = row378[row378 != 255]
print(f"  Row 378 non-255 count: {len(non255_378)}")
print(f"  Row 378 non-255 values: {sorted(non255_378.tolist())}")

print("\n=== DONE ===")
