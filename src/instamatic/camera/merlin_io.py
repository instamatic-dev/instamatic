from __future__ import annotations

import os
from typing import List

import numpy as np


class MIBProperties:
    """Class covering Merlin MIB file properties."""

    def __init__(self, head=List[str]):
        """Initialisation of default MIB properties.

        Single detector, 1 frame, 12 bit
        """
        self.path = ''
        self.buffer = True
        self.merlin_size = (int(head[4]), int(head[5]))

        # test if single or quad
        if head[2] == '00384':
            self.headsize = 384
            self.single = True
            self.quad = False
        elif head[2] == '00768':
            self.headsize = 768
            self.single = False
            self.quad = True

        self.raw = head[6] == 'R64'

        if not self.raw:
            if head[6] == 'U08':
                self.pixeltype = np.dtype('uint8')
                self.dyn_range = '1 or 6-bit'
            elif head[6] == 'U16':
                self.pixeltype = np.dtype('>u2')
                self.dyn_range = '12-bit'
            elif head[6] == 'U32':
                self.pixeltype = np.dtype('>u4')
                self.dyn_range = '24-bit'
        else:
            self.dyn_range = '12-bit'
            self.pixeltype = np.uint16

        self.packed = False
        self.offset = 0
        self.addCross = False
        self.scan_size = (1, 1)
        self.xy = 1
        self.numberOfFramesInFile = 1
        self.gap = 0
        self.quadscale = 1

        if head[7].endswith('2x2'):
            self.detectorgeometry = '2x2'
        elif head[7].endswith('Nx1'):
            self.detectorgeometry = 'Nx1'
        else:
            self.detectorgeometry = '1x1'

        self.frameDouble = 1
        self.roi_rows = 256

    def show(self):
        """Show current properties of the Merlin file.

        Use get_mib_properties(path/buffer) to populate
        """
        if not self.buffer:
            print(f'\nPath: {self.path}')
        else:
            print('\nData is from a buffer')
        if self.single:
            print('\tData is single')
        if self.quad:
            print('\tData is quad')
            print(f'\tDetector geometry {self.detectorgeometry}')
        print(f'\tData pixel size {self.merlin_size}')
        if self.raw:
            print('\tData is RAW')
        else:
            print('\tData is processed')

        print(f'\tPixel type: {np.dtype(self.pixeltype)}')
        print(f'\tDynamic range: {self.dyn_range}')
        print(f'\tHeader size: {self.headsize} bytes')
        print(f'\tNumber of frames to be read: {self.xy}')

    @classmethod
    def from_buffer(cls, buffer: bytes):
        """Return MIB properties from buffer."""
        head = buffer[:384].decode().split(',')
        return cls(head)


def load_mib(buffer: bytes, skip: int = 0):
    """Load Quantum Detectors MIB file from a memory buffer.

    skip : int, optional
        Skip first n bytes.
    """
    buffer = buffer[skip:]

    assert isinstance(buffer, (bytes, bytearray))

    props = MIBProperties.from_buffer(buffer)

    merlin_frame_dtype = np.dtype(
        [
            ('header', np.bytes_, props.headsize),
            ('data', props.pixeltype, props.merlin_size),
        ]
    )

    assert (
        len(buffer) % merlin_frame_dtype.itemsize == 0
    ), 'buffer size must be a multiple of item size'

    data = np.frombuffer(
        buffer,
        dtype=merlin_frame_dtype,
        count=-1,
        offset=0,
    )

    return data['data']
