from PIL import Image
import numpy as np
from scipy import ndimage

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl11.png')
arr = np.array(img)
gray = arr[:,:,0].astype(np.uint8)

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

# 12-building segmentation (from the earlier pzl11_schemes.py)
# heights: [167,245,144,212,292,106,250,220,137,208,144,226]
# widths: [217,96,86,91,176,99,107,97,159,111,97,100] (from 14-building segmentation, first 12)
H12 = [167,245,144,212,292,106,250,220,137,208,144,226]
W12 = [217,96,86,91,176,99,107,97,159,111,97,100]

# Test 1: 12 building heights as raw bytes (each height is 1-3 bytes)
print("=== TEST 1: 12 building heights as 1-byte values ===")
# Truncate heights to 1 byte (mod 256)
h1 = [(h % 256) for h in H12]
raw1 = bytearray(h1)
try_bytes(raw1, "12 building heights (1-byte mod 256)")

# Test 2: 12 building widths as 1-byte values
print("\n=== TEST 2: 12 building widths as 1-byte values ===")
w1 = [w % 256 for w in W12]
raw2 = bytearray(w1)
try_bytes(raw2, "12 building widths (1-byte mod 256)")

# Test 3: Combined H,W,H,W,... as 1-byte values
print("\n=== TEST 3: Combined H,W,H,W as 1-byte values ===")
raw3 = bytearray()
for h, w in zip(H12, W12):
    raw3.append(h % 256)
    raw3.append(w % 256)
try_bytes(raw3, "combined H,W (1-byte mod 256)")

# Test 4: 28-digit sequence from earlier analysis
print("\n=== TEST 4: 28-digit sequence (bar graph) as bytes ===")
digits = [0,5,2,3,2,3,3,4,6,5,9,5,6,6,2,0,3,7,3,4,4,3,4,2,0,4,6,3]
raw4 = bytearray(digits)
try_bytes(raw4, "28-digit bar graph sequence (raw)")

# Test 5: 28-digit sequence as bytes with digit+48 conversion
print("\n=== TEST 5: 28-digit sequence as ASCII digits ===")
raw5 = bytearray(d + 48 for d in digits)
try_bytes(raw5, "28-digit bar graph (ASCII digits)")

# Test 6: Building heights as 2-byte LE values
print("\n=== TEST 6: 12 building heights as 2-byte LE ===")
raw6 = bytearray()
for h in H12:
    raw6.append(h & 0xFF)
    raw6.append((h >> 8) & 0xFF)
try_bytes(raw6, "12 building heights (2-byte LE)")

# Test 7: Building widths as 2-byte LE
print("\n=== TEST 7: 12 building widths as 2-byte LE ===")
raw7 = bytearray()
for w in W12:
    raw7.append(w & 0xFF)
    raw7.append((w >> 8) & 0xFF)
try_bytes(raw7, "12 building widths (2-byte LE)")

# Test 8: Combined H,W,H,W as 2-byte LE
print("\n=== TEST 8: Combined H,W,H,W as 2-byte LE ===")
raw8 = bytearray()
for h, w in zip(H12, W12):
    raw8.append(w & 0xFF)
    raw8.append((w >> 8) & 0xFF)
    raw8.append(h & 0xFF)
    raw8.append((h >> 8) & 0xFF)
try_bytes(raw8, "combined H,W (2-byte LE)")

# Test 9: 14-building segmentation (from earlier analysis)
print("\n=== TEST 9: 14-building widths as 1-byte values ===")
W14 = [217,96,86,91,176,99,107,97,159,111,97,100,69,67]
w14 = [w % 256 for w in W14]
raw9 = bytearray(w14)
try_bytes(raw9, "14 building widths (1-byte mod 256)")

# Test 10: 14-building heights as 1-byte values
# From earlier analysis: boundaries x=[14,231,327,413,504,680,779,886,983,1142,1253,1350,1450,1519,1586]
# The heights were measured as: 167,245,144,212,292,106,250,220,137,208,144,226 (12 buildings)
# For 14 buildings, we need to segment differently
# Let me compute the heights from the image
print("\n=== TEST 10: Compute 14 building heights from image ===")
# Find the roofline (topmost dark pixel per column for the building region)
# The building region is the right portion of the image
# Use the boundaries from the earlier analysis
boundaries_x = [14,231,327,413,504,680,779,886,983,1142,1253,1350,1450,1519,1586]
heights_14 = []
for i in range(len(boundaries_x)-1):
    x0, x1 = boundaries_x[i], boundaries_x[i+1]
    # Find the topmost dark pixel in this column range
    col_range = gray[:, x0:x1]
    dark_rows = np.where(col_range < 128)[0]
    if len(dark_rows) > 0:
        heights_14.append(int(dark_rows.max() - dark_rows.min()))
    else:
        heights_14.append(0)
print(f"14 building heights: {heights_14}")
# Clip to 1 byte
h14 = [min(h, 255) for h in heights_14]
raw10 = bytearray(h14)
try_bytes(raw10, "14 building heights (1-byte)")

print("\n=== ALL TESTS COMPLETE ===")
