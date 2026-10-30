import re, base64, struct
html = open('/home/sudosudo/.openclaw/workspace/puzzle_10_direct.html', encoding='utf-8', errors='replace').read()
# Find the big img src
m = re.search(r'<img alt="puz10" src="data:image/png;base64,([^"]+)"', html)
if m:
    u = m.group(1)
    # fix padding
    pad = len(u) % 4
    if pad: u += '=' * (4 - pad)
    data = base64.b64decode(u)
    fn = '/home/sudosudo/.openclaw/workspace/puzzle10_main.png'
    open(fn, 'wb').write(data)
    w, h = struct.unpack('>II', data[16:24])
    print(f"main image: {len(data)} bytes, {w}x{h} -> {fn}")
else:
    print("not found")
