import sys

import matplotlib.pyplot as plt

from instamatic.formats import read_image


def main():
    try:
        fn = sys.argv[1]
    except BaseException:
        print("Usage: instamatic.viewer IMG.tiff")
        exit()

    img, h = read_image(fn)

    print(f"""Loading data: {fn}
        size: {img.nbytes / 1024} kB
       shape: {img.shape}
       range: {img.min()}-{img.max()}
       dtype: {img.dtype}
""")

    max_len = max([len(s) for s in h.keys()])

    fmt = f"{{:{max_len}s}} = {{}}"
    for key in sorted(h.keys()):
        print(fmt.format(key, h[key]))

    plt.imshow(img, cmap="gray")
    plt.title(fn)
    plt.show()


if __name__ == '__main__':
    main()
