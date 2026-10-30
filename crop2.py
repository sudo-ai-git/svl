from PIL import Image
img = Image.open('/home/sudosudo/.openclaw/workspace/pzl_10_assembled.jpg').convert('RGB')
print("assembled size:", img.size)
w, h = img.size  # 1704x1122
# From the reading: dice on left, numbers center-left, logo center, [0-19] right, key bottom
# Crop left third (dice + numbers)
img.crop((0, 0, int(w*0.45), h)).save('/home/sudosudo/.openclaw/workspace/pzl10_left.png')
# center (logo)
img.crop((int(w*0.25), 0, int(w*0.72), h)).save('/home/sudosudo/.openclaw/workspace/pzl10_center.png')
# right ([0-19] + key)
img.crop((int(w*0.55), 0, w, h)).save('/home/sudosudo/.openclaw/workspace/pzl10_right.png')
# bottom (key)
img.crop((0, int(h*0.5), w, h)).save('/home/sudosudo/.openclaw/workspace/pzl10_bottom.png')
print("saved")
