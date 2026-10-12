from __future__ import annotations

import numpy as np

from instamatic.camera.serval_movie_deserializer import ServalMovieDeserializer

rng = np.random.default_rng(1337)
json_image = rng.integers(low=0, high=256, size=(512, 512), dtype=np.uint16).astype('>u2')
json_header = b"""{
    "timeAtFrame": 1655990130.181,
    "frameNumber": 14,
    "measurementID": "None",
    "dataSize": 524288,
    "bitDepth": 16,
    "isPreviewSampled": true,
    "thresholdID": 0,
    "pixelEventNumber": 0,
    "tdc1EventNumber": 0,
    "tdc2EventNumber": 0,
    "integrationSize": 0,
    "integrationMode": "None",
    "width": 512,
    "height": 512,
    "corrections": []
}\n"""
json_bytes = json_header + bytearray(json_image.data)
movie_bufsize = 2 * 4 * 512 * 512


class MockSocket:
    """A simple socket-like object that serves predefined bytes."""

    def __init__(self, data: bytes):
        self._buf = memoryview(data)
        self._offset = 0

    def recv_into(self, b: memoryview) -> int:
        n = min(len(b), len(self._buf) - self._offset)
        if n == 0:
            return 0
        b[:n] = self._buf[self._offset : self._offset + n]
        self._offset += n
        return n


def test_serval_movie_deserializer1() -> None:
    """Check that ServalMovieDeserializer can yield one image correctly."""
    sock = MockSocket(json_bytes)
    smd = ServalMovieDeserializer(sock, n_frames=1, bufsize=movie_bufsize)  # type: ignore
    image = next(smd)
    np.testing.assert_array_equal(image, json_image)


def test_serval_movie_deserializer100() -> None:
    """Check that ServalMovieDeserializer can yield 100 images correctly."""
    sock = MockSocket(json_bytes * 100)
    smd = ServalMovieDeserializer(sock, n_frames=100, bufsize=movie_bufsize)  # type: ignore
    for image in smd:
        np.testing.assert_array_equal(image, json_image)
