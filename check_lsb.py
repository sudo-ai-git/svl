from PIL import Image
import numpy as np

# LSB steganography check on the authoritative image
img = Image.open('/home/sudosudo/.openclaw/workspace/pzl10_authoritative.png').convert('RGB')
a = np.array(img)
print("shape:", a.shape)

# Extract LSBs from each channel
for ch, name in enumerate(['R', 'G', 'B']):
    lsb = a[:,:,ch] & 1
    # Try to decode as ASCII (8 bits per char, MSB first)
    flat = lsb.flatten()
    chars = []
    for i in range(0, min(len(flat), 8000), 8):
        byte = 0
        for j in range(8):
            if i+j < len(flat):
                byte = (byte << 1) | flat[i+j]
        chars.append(chr(byte) if 32 <= byte < 127 else '.')
    text = ''.join(chars)
    # Check for readable text
    readable = sum(1 for c in text[:200] if c.isalnum() or c in ' .,!?-')
    print(f"{name} LSB: {readable}/200 readable, first 100: {text[:100]}")

# Also check 2-bit LSB
for ch, name in enumerate(['R', 'G', 'B']):
    lsb2 = a[:,:,ch] & 3
    flat = lsb2.flatten()
    chars = []
    for i in range(0, min(len(flat), 4000), 4):
        byte = 0
        for j in range(4):
            if i+j < len(flat):
                byte = (byte << 2) | flat[i+j]
        chars.append(chr(byte) if 32 <= byte < 127 else '.')
    text = ''.join(chars)
    readable = sum(1 for c in text[:200] if c.isalnum() or c in ' .,!?-')
    print(f"{name} 2-bit LSB: {readable}/200 readable, first 100: {text[:100]}")
