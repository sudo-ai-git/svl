from PIL import Image
import numpy as np

p = '/home/sudosudo/.openclaw/workspace/pzl10_authoritative.png'
img = Image.open(p)
print("mode:", img.mode, "size:", img.size)
a = np.array(img)
print("shape:", a.shape, "dtype:", a.dtype)

if a.shape[2] == 4:
    alpha = a[:,:,3]
    print("alpha unique values:", np.unique(alpha)[:20], "...", "count unique:", len(np.unique(alpha)))
    print("alpha min/max/mean:", alpha.min(), alpha.max(), alpha.mean())
    # Save alpha as an image
    Image.fromarray(alpha).save('/home/sudosudo/.openclaw/workspace/pzl10_alpha.png')
    # Check if alpha is all 255 (opaque)
    print("all opaque (255)?", (alpha==255).all())
    # Save alpha scaled up
    Image.fromarray(alpha).resize((2400,1544), Image.NEAREST).save('/home/sudosudo/.openclaw/workspace/pzl10_alpha_2x.png')
    # LSB of alpha
    lsb = (alpha & 1).astype(np.uint8)*255
    Image.fromarray(lsb).save('/home/sudosudo/.openclaw/workspace/pzl10_alpha_lsb.png')
    print("alpha LSB ones:", int((alpha&1).sum()), "of", alpha.size)
else:
    print("no alpha channel")
