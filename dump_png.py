#!/usr/bin/env python3
"""Restored PNG chunk dump (PNG was corrupted in earlier turns)."""
import struct
from PIL import Image
f = open('/home/sudosudo/.openclaw/workspace/pzl11.png','rb')
data = f.read(); f.close()
print("file size:", len(data))
pos = 8; n=0
while pos+8 <= len(data):
    length = struct.unpack('>I', data[pos:pos+4])[0]
    ctype = data[pos+4:pos+8].decode('latin1', errors='replace')
    chunk_data = data[pos+8:pos+8+length]
    print(f"@{pos:>9}: {ctype} len={length} data={chunk_data[:70]!r}")
    if ctype in ('IDAT','tEXt','zTXt','iCCP','iTXt','bKGD','pHYs','gAMA','cHRM','sRGB','iTXt'):
        if ctype == 'IDAT':
            print("     >! IDAT IMAGE DATA <!")
        else:
            print("     >! HIDDEN METADATA {ctype} <!")
    pos += 12 + length; n += 1
print("chunks:", n)
