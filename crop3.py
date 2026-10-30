from PIL import Image
img = Image.open('/home/sudosudo/.openclaw/workspace/pzl10_authoritative.png').convert('RGB')
# key regions from segmentation
regions = {
    'dice':   (14, 195, 402, 461),      # comp 384 (left area)
    'logo':   (252, 114, 580, 373),     # comp 215
    'right':  (890, 354, 1199, 547),    # comp 488
    'bottomL':(116, 448, 547, 761),     # comp 536
    'bottomR':(547, 575, 776, 738),     # comp 636
}
for name, box in regions.items():
    c = img.crop(box)
    c.resize((c.size[0]*3, c.size[1]*3), Image.LANCZOS).save(f'/home/sudosudo/.openclaw/workspace/reg_{name}.png')
    print(name, box, "->", c.size)
