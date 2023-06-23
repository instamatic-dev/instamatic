import numpy as np
from skimage.transform import resize

from instamatic.tools import find_defocused_image_center


def img_preproc(img, size=(80, 80)):
    crystal_pos, r = find_defocused_image_center(img)
    crystal_pos = crystal_pos[::-1]

    if r[0] <= r[1]:
        window_size = r[0] * 2
    else:
        window_size = r[1] * 2

    a1 = int(crystal_pos[0] - window_size / 2)
    b1 = int(crystal_pos[0] + window_size / 2)
    a2 = int(crystal_pos[1] - window_size / 2)
    b2 = int(crystal_pos[1] + window_size / 2)

    img_cropped = img[a1:b1, a2:b2]
    img_resized = resize(img_cropped, size)
    img_resized = np.interp(img_resized, (img_resized.min(), img_resized.max()), (0, 255))
    return img_resized.astype(np.int16)
