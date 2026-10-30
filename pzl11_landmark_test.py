from PIL import Image
import numpy as np

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
alpha = arr[:,:,1].astype(np.uint8)

# Extract alpha values at landmark indices
alpha_flat = alpha.flatten()
print(f"Alpha channel shape: {alpha.shape}, size: {alpha_flat.size}")

print("\n=== TEST 1: Alpha values at landmark indices ===")
landmarks = ['ETH=11', 'BOAT=43', 'SEED=154', 'KEY=314']
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    val = alpha_flat[idx]
    print(f"  {name} at idx {idx}: alpha={val} (0x{val:02x})")

# Test: the alpha values at these indices as bytes
landmark_bytes = bytearray()
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    landmark_bytes.append(alpha_flat[idx])
print(f"\nLandmark bytes: {bytes(landmark_bytes).hex()}")

# Test: the raw alpha values at these indices (not just the values, but the surrounding bytes)
print("\n=== TEST 2: Alpha values at landmark indices (raw 8-bit) ==="
)
landmark_raw = bytearray()
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    landmark_raw.append(alpha_flat[idx])
print(f"Landmark raw: {bytes(landmark_raw).hex()}")

# Test: the 4-byte sequence as 32-byte (padded)
print("\n=== TEST 3: 4-byte sequence padded to 32 bytes ==="
)
padded = bytearray(landmark_raw)
while len(padded) < 32:
    padded.append(0)
print(f"Padded: {bytes(padded).hex()}")

# Test: the alpha values around each landmark
print("\n=== TEST 4: Alpha values around each landmark (20 bytes each) ==="
)
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    start = max(0, idx - 10)
    end = min(len(alpha_flat), idx + 10)
    vals = alpha_flat[start:end]
    print(f"  {name}: {vals.tolist()}")

# Test: the 4x20-byte blocks around landmarks
print("\n=== TEST 5: 4x20-byte blocks around landmarks ==="
)
for name, idx in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    start = max(0, idx - 10)
    end = min(len(alpha_flat), idx + 10)
    vals = alpha_flat[start:end]
    print(f"  {name} idx {idx}: {vals.tolist()}")

# Test: Keccak-256 of row-0 pixel block 1013-1400 (from SKILL.md)
# Row 0 = alpha channel values at index 0-1400 or so
# "row-0 pixel block 1013-1400" - this is ambiguous. Let me test the alpha values at indices 1013-1400
print("\n=== TEST 6: Alpha values at indices 1013-1400 (287 values) ==="
)
block = alpha_flat[1013:1400]
print(f"  Block size: {len(block)}, values: {block.tolist()}")

# Test: the first 32 bytes of the block
print("\n=== TEST 7: First 32 bytes of block 1013-1400 ==="
)
first32 = block[:32]
print(f"  First 32 bytes: {first32.tolist()}")

# Test: the alpha values at the mnemonic offset 59
print("\n=== TEST 8: Alpha values at offset 59 (mnemonic location) ==="
)
mnemonic_off = alpha_flat[59]
print(f"  Alpha at offset 59: {mnemonic_off} (0x{mnemonic_off:02x})")

# Test: the mnemonic words around offset 59
print("\n=== TEST 9: Alpha values at offsets 50-70 ==="
)
vals_50_70 = alpha_flat[50:70]
print(f"  Alpha at 50-70: {vals_50_70.tolist()}")

# Test: the grayscale values at row 0 (y=0)
print("\n=== TEST 10: Gray channel row 0 (y=0) ==="
)
gray = arr[:,:,0].astype(np.uint8)
row0 = gray[0, :]
print(f"  Row 0 size: {len(row0)}, first 32 bytes: {row0[:32].tolist()}")

# Test: the alpha values at row 0
print("\n=== TEST 11: Alpha channel row 0 (y=0) ==="
)
alpha_row0 = alpha[0, :]
print(f"  Row 0 size: {len(alpha_row0)}, first 32 bytes: {alpha_row0[:32].tolist()}")

# Test: combine row0 gray and alpha as data
print("\n=== TEST 12: Row 0 combined (gray + alpha) as bytes ==="
)
combined = bytearray()
combined.extend(row0[:128])
combined.extend(alpha_row0[:128])
print(f"  Combined size: {len(combined)}")

print("\n=== ALL TESTS COMPLETE ===")
