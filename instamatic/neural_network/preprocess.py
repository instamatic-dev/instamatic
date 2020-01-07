import numpy as np
from skimage.transform import resize


def preprocess(image, n_std=4):
    x, y = np.where(image > np.max(image) * 0.99)
    c_x, c_y = int(np.mean(x)), int(np.mean(y))
    size = 200
    x_min = c_x - size
    x_max = c_x + size
    if x_min < 0:
        x_min = 0
        x_max = size * 2
    if x_max >= 515:
        x_min = 514 - size * 2
        x_max = 514
    y_min = c_y - size
    y_max = c_y + size
    if y_min < 0:
        y_min = 0
        y_max = size * 2
    if y_max >= 515:
        y_min = 514 - size * 2
        y_max = 514

    s_image = np.copy(image[x_min:x_max, y_min:y_max])
    mean = np.mean(s_image)
    std = np.std(s_image)
    s_image[s_image > (mean + n_std * std)] = mean + n_std * std
    div = (np.max(s_image) - np.min(s_image))
    if div == 0:
        div = 1
    s_image = (s_image - np.min(s_image)) / div
    red_s_image = resize(s_image, [150, 150], mode='constant')
    return red_s_image.reshape((150, 150, 1))
