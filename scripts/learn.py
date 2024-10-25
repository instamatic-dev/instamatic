from __future__ import annotations

import csv
import glob
import sys
from pathlib import Path

from tqdm.auto import tqdm

from instamatic import neural_network
from instamatic.formats import *


def closest_distance(node, nodes):
    """Get shortest between a node and a list of nodes (that includes the given
    node)"""
    nodes = np.asarray(nodes)
    dist_2 = np.sum((nodes - node) ** 2, axis=1)
    return np.sort(dist_2)[1] ** 0.5


def find_isolated_crystals(fns, min_separation=1.5, boundary=0.5, plot=False):
    """Find crystals that are at least `min_separation` in micrometers away
    from other crystals."""
    isolated = []

    for fn in fns:
        img, h = read_hdf5(fn)
        coords = h['exp_crystal_coords']

        if len(coords) == 0:
            continue

        # apply calibration
        shape = h['ImageCameraDimensions']
        dimensions = h['ImageDimensions']
        calibrated_coords = np.multiply(coords, dimensions / shape)

        boundary_px = shape * boundary / dimensions

        objects = []
        n_isolated = 0

        for i, (coord, calibrated_coord) in enumerate(zip(coords, calibrated_coords)):
            try:
                min_dist = closest_distance(calibrated_coord, calibrated_coords)
            except IndexError:
                min_dist = 9999

            x, y = coord

            if not (boundary_px[0] < x < shape[0] - boundary_px[0]):
                objects.append((x, y, 'orange'))
            elif not (boundary_px[1] < y < shape[1] - boundary_px[1]):
                objects.append((x, y, 'orange'))
            elif min_dist > min_separation:
                objects.append((x, y, 'red'))
                n_isolated += 1
                p = Path(fn)
                isolated.append(p.parents[1] / 'data' / f'{p.stem}_{i:04d}{p.suffix}')
            else:
                objects.append((x, y, 'blue'))

        if plot and n_isolated:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots()
            ax.imshow(img)

            for x, y, color in objects:
                ax.scatter(y, x, color=color)

            # diff_img, _ = read_hdf5(isolated[-1])
            # ax2 = inset_locator.inset_axes(ax, "40%", "40%", loc=3)
            # ax2.imshow(diff_img, vmax=np.percentile(diff_img, 99))
            # ax2.axis("off")

            ax.axis('off')
            ax.set_title(fn)
            plt.show()

    return isolated


def main(file_pattern):
    image_fns = glob.glob(file_pattern)
    print(len(image_fns), 'Images')

    diff_fns = find_isolated_crystals(image_fns)
    print(len(diff_fns), 'Patterns from isolated crystals')

    lst = []
    for fn in tqdm(diff_fns):
        img, h = read_hdf5(fn)

        frame = int(str(fn)[-12:-8])
        number = int(str(fn)[-7:-3])

        img_processed = neural_network.preprocess(img.astype(float))
        prediction = neural_network.predict(img_processed)

        if prediction < 0.5:
            # print fn, "prediction too low", prediction
            continue

        try:
            size = h['total_area_micrometer'] / h['crystal_clusters']  # micrometer^2
        except KeyError:
            # old data formats don't have this information
            size = 0.0

        try:
            dx, dy = h['exp_hole_offset']
            cx, cy = h['exp_hole_center']
        except KeyError:
            dx, dy = h['exp_scan_offset']
            cx, cy = h['exp_scan_center']

        prediction = round(prediction, 4)
        size = round(size, 4)
        x = int(cx + dx)
        y = int(cy + dy)

        lst.append((fn.absolute(), frame, number, prediction, size, x, y))

    with open('learning.csv', 'w', newline='') as csvfile:
        # writer = csv.DictWriter(csvfile, fieldnames=["filename", "frame", "number", "quality", "size", "xpos", "ypos"])
        # writer.writeheader()
        writer = csv.writer(csvfile)
        writer.writerows(lst)


def main_entry():
    import argparse

    description = (
        """Predict whether a crystal is of good or bad quality by its diffraction pattern."""
    )

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'args',
        type=str,
        nargs=1,
        metavar='PAT',
        help='File pattern to glob for images (HDF5), i.e. `images/*.h5`.',
    )

    options = parser.parse_args()
    args = options.args

    if args:
        pattern = args[0]
    else:
        pattern = 'images/*.h5'

    main(pattern)


if __name__ == '__main__':
    main_entry()
