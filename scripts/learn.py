import glob
from instamatic.formats import *
from instamatic import neural_network
import csv
import os, sys

import tqdm

def main(file_pattern):
    fns = glob.glob(file_pattern)
    
    lst = []
    for fn in tqdm.tqdm(fns):
        img, h = read_hdf5(fn)
    
        frame = int(fn[-12:-8])
        number = int(fn[-7:-3])

        img_processed = neural_network.preprocess(img.astype(np.float))
        quality = neural_network.predict(img_processed)
        
        size = 0
    
        try:
            dx, dy = h["exp_hole_offset"]
            cx, cy = h["exp_hole_center"]
        except KeyError:
            dx, dy = h["exp_scan_offset"]
            cx, cy = h["exp_scan_center"]

        quality = round(quality, 4)
        size = round(size, 4)
        x = int(cx + dx)
        y = int(cy + dy)
        
        lst.append((os.path.abspath(fn), frame, number, quality, size, x, y))
    
    with open('learning.csv', 'wb') as csvfile:
        # writer = csv.DictWriter(csvfile, fieldnames=["filename", "frame", "number", "quality", "size", "xpos", "ypos"])
        # writer.writeheader()
        writer = csv.writer(csvfile)
        writer.writerows(lst)


def main_entry():
    if len(sys.argv) > 1:
        pattern = sys.argv[1]
    else:
        pattern = "data/*.h5"
    
    main(pattern)


if __name__ == '__main__':
    main_entry()