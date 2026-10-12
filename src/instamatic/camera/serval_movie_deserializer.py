from __future__ import annotations

import json
import socket
from math import prod
from typing import Iterator

import numpy as np
from typing_extensions import TypeAlias

Movie: TypeAlias = Iterator[np.ndarray]


class ServalMovieDeserializer(Movie):
    """Deserializes Serval camera TCP byte stream from socket into images."""

    def __init__(self, sock: socket.socket, n_frames: int, bufsize: int) -> None:
        self.sock: socket.socket = sock
        self.buffer = bytearray(bufsize)
        self.view = memoryview(self.buffer)
        self.used: int = 0
        self.i_frame: int = 0
        self.n_frames: int = n_frames
        self.shape: tuple[int, int] = (0, 0)
        self.size: int = 0
        self.dtype: np.dtype = np.dtype(np.uint32)

    def _receive_more(self) -> None:
        """Attempt to receive bytes from the socket into free buffer space."""
        recv_len = self.sock.recv_into(self.view[self.used :])
        if not recv_len:
            raise EOFError
        self.used += recv_len

    def _receive_until(self, token: bytes) -> int:
        """Recv data until `token` is found, return index after the token."""
        while True:
            token_idx = self.buffer.find(token, 0, self.used)
            if token_idx >= 0:
                return token_idx + len(token)
            self._receive_more()

    def _parse_header(self, header_size: int) -> None:
        """Read shape, size, dtype of all images from the 1st frame header."""
        header_str = self.buffer[:header_size].decode('utf-8')
        header_dict = json.loads(header_str)
        bit_depth = header_dict['bitDepth']
        self.shape = (header_dict['height'], header_dict['width'])
        self.dtype = np.dtype(f'uint{bit_depth}').newbyteorder('>')
        self.size = header_dict.get('dataSize', prod(self.shape) * self.dtype.itemsize)

    def __next__(self) -> np.ndarray:
        """Recv as much data as needed, return next frame from TCP stream."""
        if self.i_frame >= self.n_frames:
            raise StopIteration
        header_end = self._receive_until(b'}') + 1  # json image never nests "}"
        if self.i_frame == 0:
            self._parse_header(header_end)
        while self.used < header_end + self.size:
            self._receive_more()
        i, j = header_end, header_end + self.size
        frame = np.frombuffer(self.buffer[i:j], dtype=self.dtype).reshape(self.shape).copy()

        self.buffer[: self.used - j] = self.buffer[j : self.used]
        self.used -= j
        self.i_frame += 1
        return frame
