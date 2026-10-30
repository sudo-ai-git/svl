from PIL import Image
import numpy as np

img = Image.open('/home/sudosudo/.openclaw/workspace/pzl10_authoritative.png').convert('RGB')
a = np.array(img)

# Crop the regions around each key object and save enlarged, high-contrast versions
# From segmentation: 5 main "keys" likely. Let's save the whole thing upscaled 2x
img.resize((2400, 1544), Image.LANCZOS).save('/home/sudosudo/.openclaw/workspace/pzl10_2x.png')

# Also save quadrants at 2x
w, h = img.size
regions = {
    'tl': (0, 0, 600, 400),
    'tr': (600, 0, 1200, 400),
    'bl': (0, 400, 600, 772),
    'br': (600, 400, 1200, 772),
}
for name, box in regions.items():
    img.crop(box).resize(((box[2]-box[0])*2, (box[3]-box[1])*2), Image.LANCZOS).save(f'/home/sudosudo/.openclaw/workspace/pzl10_{name}.png')
print("saved regions")
