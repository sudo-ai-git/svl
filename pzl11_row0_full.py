from PIL import Image
import numpy as np
import hashlib

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)
alpha = arr[:,:,1].astype(np.uint8)

# Row 0 non-255 gray values
row0_gray = gray[0, :]
row0_non255 = row0_gray[row0_gray != 255]
print(f"Row 0 non-255 count: {len(row0_non255)}")
print(f"Row 0 non-255 values: {row0_non255.tolist()}")

TARGET = bytes.fromhex('ff2142e98e09b5344994f9beb9c56c95506b9f17')

def try_bytes(raw, name):
    if len(raw) < 32:
        print(f"{name}: too short ({len(raw)} bytes)")
        return False
    found = False
    for start in range(len(raw) - 32 + 1):
        if raw[start:start+32] == TARGET:
            print(f"TARGET FOUND at offset {start} in {name}")
            return True
    print(f"{name}: NOT FOUND ({len(raw)} bytes)")
    return False

# Test 1: Row 0 non-255 gray values as 1-byte
print("\n=== TEST 1: Row 0 non-255 gray (1-byte) ==="
)
try_bytes(bytearray(row0_non255.tolist()), "row 0 non-255 gray (1-byte)")

# Test 2: Full row 0 gray values (all 1600 bytes)
print("\n=== TEST 2: Row 0 gray full row ==="
)
try_bytes(row0_gray.tobytes(), "row 0 gray full row")

# Test 3: Row 0 gray values, excluding 255s, as raw bytes
print("\n=== TEST 3: Row 0 non-255 gray (raw bytes) ==="
)
try_bytes(row0_non255.tobytes(), "row 0 non-255 gray (raw)")

# Test 4: Row 0 gray values grouped into 40 words (each word = 2 bytes from 5 gray values)
print("\n=== TEST 4: Row 0 grouped into 40 words (2-byte LE) ==="
)
# Group the 147 non-255 values into 40 words (2-byte LE each = 80 bytes)
# But we have 147 values, so use all of them
words = []
for i in range(0, len(row0_non255) - 1, 2):
    w = (row0_non255[i] << 8) | row0_non255[i+1]
    words.append(w)
raw4 = bytearray(words)
print(f"  Grouped words: {len(words)} (80 bytes)")
try_bytes(raw4, "row 0 grouped (2-byte LE words)")

# Test 5: Row 0 gray values as 8-bit with padding to 256 bytes
print("\n=== TEST 5: Row 0 gray (padded to 256 bytes) ==="
)
padded = bytearray(row0_gray.tolist())
while len(padded) < 256:
    padded.append(0)
try_bytes(padded, "row 0 gray padded to 256")

# Test 6: Alpha values at specific x positions in row 0
# The landmarks were at x=11, 43, 154, 314
print("\n=== TEST 6: Alpha values at landmark x positions in row 0 ==="
)
# These are all 255 in row 0
for name, x in [('ETH', 11), ('BOAT', 43), ('SEED', 154), ('KEY', 314)]:
    print(f"  {name}: alpha={alpha[0, x]}, gray={gray[0, x]}")

# Test 7: Combine row 0 gray and alpha (interleaved)
print("\n=== TEST 7: Row 0 interleaved gray+alpha ==="
)
combined = bytearray()
for i in range(1600):
    combined.append(gray[0, i])
    combined.append(alpha[0, i])
print(f"  Combined size: {len(combined)} bytes")
try_bytes(combined, "row 0 interleaved gray+alpha")

# Test 8: Row 0 grayscale as a bitstream (each 8 values -> 1 byte)
print("\n=== TEST 8: Row 0 grayscale as bitstream (8 values -> 1 byte) ==="
)
bitstream = bytearray()
for i in range(0, len(row0_gray) - 7, 8):
    byte = 0
    for bit in range(8):
        byte |= (row0_gray[i + bit] & 1) << (7 - bit)
    bitstream.append(byte)
print(f"  Bitstream size: {len(bitstream)} bytes")
try_bytes(bitstream, "row 0 grayscale bitstream")

# Test 9: Row 0 grayscale as 5-bit symbols (only non-255)
print("\n=== TEST 9: Row 0 non-255 grayscale as 5-bit symbols ==="
)
bits9 = []
for g in row0_non255:
    for bit in range(5):
        bits9.append((g >> bit) & 1)
nbytes9 = (len(bits9) + 7) // 8
raw9 = bytearray(nbytes9)
for i, bit in enumerate(bits9):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw9[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw9, "row 0 non-255 grayscale (5-bit)")

# Test 10: The gray values in row 0 as a continuous bitstream (8 bits per value)
print("\n=== TEST 10: Row 0 grayscale as bitstream (8 bits per value) ==="
)
bits10 = []
for g in row0_gray:
    for bit in range(8):
        bits10.append((g >> bit) & 1)
nbytes10 = (len(bits10) + 7) // 8
raw10 = bytearray(nbytes10)
for i, bit in enumerate(bits10):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw10[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw10, "row 0 grayscale bitstream (8 bits per value)")

# Test 11: The gray values in row 0 converted to 5-bit symbols (all 1600 values, skip 255)
print("\n=== TEST 11: Row 0 grayscale (skip 255s) as 5-bit symbols ==="
)
alpha_flat = alpha.flatten()
for a in alpha_flat:
    for bit in range(5):
        bits_val.append((a >> bit) & 1)
nbytes11 = (len(bits_val) + 7) // 8
raw11 = bytearray(nbytes11)
for i, bit in enumerate(bits_val):
    byte_idx = i // 8
    bit_in_byte = i % 8
    if bit:
        raw11[byte_idx] |= (1 << (7 - bit_in_byte))
try_bytes(raw11, "row 0 grayscale (skip 255s) as 5-bit")

print("\n=== ALL TESTS COMPLETE ===")
