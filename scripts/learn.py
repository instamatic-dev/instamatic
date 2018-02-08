from __future__ import division
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
        
        is_isolated = h["crystal_is_isolated"]
        if not is_isolated:
            # print fn, "not isolated"
            continue
    
        frame = int(fn[-12:-8])
        number = int(fn[-7:-3])

        img_processed = neural_network.preprocess(img.astype(np.float))
        prediction = neural_network.predict(img_processed)

        if prediction < 0.5:
            # print fn, "prediction too low", prediction
            continue

        size = h["total_area_micrometer"] / h["crystal_clusters"] # micrometer^2
    
        try:
            dx, dy = h["exp_hole_offset"]
            cx, cy = h["exp_hole_center"]
        except KeyError:
            dx, dy = h["exp_scan_offset"]
            cx, cy = h["exp_scan_center"]

        prediction = round(prediction, 4)
        size = round(size, 4)
        x = int(cx + dx)
        y = int(cy + dy)
        
        lst.append((os.path.abspath(fn), frame, number, prediction, size, x, y))

    with open('learning.csv', 'w', newline="") as csvfile:
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