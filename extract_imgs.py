import re, base64
html = open('/home/sudosudo/.openclaw/workspace/puzzle_10_direct.html', encoding='utf-8', errors='replace').read()
# Find all base64 PNG data URIs
uris = re.findall(r'data:image/png;base64,([A-Za-z0-9+/=]+)', html)
print("Found", len(uris), "PNG data URIs")
for i, u in enumerate(uris):
    data = base64.b64decode(u)
    fn = f'/home/sudosudo/.openclaw/workspace/embedded_img_{i}.png'
    open(fn, 'wb').write(data)
    print(f"  img_{i}: {len(data)} bytes -> {fn}")
    # PNG header dims
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        import struct
        w, h = struct.unpack('>II', data[16:24])
        print(f"    dims: {w}x{h}")
