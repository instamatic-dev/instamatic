from __future__ import annotations

import time

from tqdm import tqdm

global _ctrl


print('Start of script showcase_movie.py in 5 seconds.')
print('Stopping the preview for the showcase.')

with _ctrl.cam.blocked():
    print('Showcase: Collecting a 100-frame 0.1s-exposure movie')
    time.sleep(5)
    time_start = time.perf_counter()
    gen = _ctrl.get_movie(n_frames=100, exposure=0.1)
    for image, header in gen:  # tqdm(gen, unit='frame'):
        time.sleep(0)  # in contrast to pass, yields priority to other threads
    time_end = time.perf_counter()
    print(f'Time taken: {time_end - time_start} seconds.')

    print('Reference: Collecting 100 images with 0.1 s exposure')
    time.sleep(5)
    time_start = time.perf_counter()
    for _ in range(100):  # tqdm(range(100), unit='frame'):
        _ctrl.get_image(exposure=0.1)
    time_end = time.perf_counter()
    print(f'Time taken: {time_end - time_start} seconds.')

    print('Bonus: A 100-frame 0.1s-exposure movie w tqdm')
    time.sleep(5)
    time_start = time.perf_counter()
    gen = _ctrl.get_movie(n_frames=100, exposure=0.1)
    for image, header in tqdm(gen, unit='frame'):
        time.sleep(0)
    time_end = time.perf_counter()
    print(f'Time taken: {time_end - time_start} seconds.')

print('End of script showcase_movie.py')
