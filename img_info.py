from PIL import Image
import os

for fname in ['pzl10_key_1.jpg', 'pzl10_key_2.jpg', 'pzl10_key_3.jpg', 'pzl10_key_4.jpg', 'pzl10_key_5.jpg']:
    img = Image.open('/home/sudosudo/.openclaw/workspace/' + fname)
    print(f'{fname}: size={img.size}, mode={img.mode}')
    rgb = img.convert('RGB')
    print(f'  corner TL={rgb.getpixel((0,0))} TR={rgb.getpixel((img.size[0]-1,0))}')
