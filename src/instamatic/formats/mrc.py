# https://github.com/ezralanglois/arachnid/blob/master/arachnid/core/image/formats/mrc.py
# Licenced under GPL
"""Read and write images in the MRC format.

.. todo:: define arachnid header and map to mrc

.. note::

    This code is heavily modified version of the MRC parser/writer
    found in the Scripps Appion program.


.. Created on Aug 9, 2012
.. codeauthor:: Robert Langlois <rl2528@columbia.edu>
"""

from __future__ import annotations

import logging
import os
import sys

import numpy

from . import util

# import util

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)

mrc2numpy = {
    0: numpy.int8,
    1: numpy.int16,
    2: numpy.float32,
    3: numpy.dtype([('real', numpy.int16), ('imag', numpy.int16)]),
    # complex made of two int16.  No such thing in numpy
    #     however, we could manually build a complex array by reading two
    #     int16 arrays somehow.
    4: numpy.complex64,
    6: numpy.uint16,  # according to UCSF
    7: numpy.uint8,  # according to UCSF
}

# mapping of numpy type to MRC mode
numpy2mrc = {
    # convert these to int8
    numpy.int8: 0,
    #    numpy.uint8: 0,
    numpy.bool_: 0,
    # convert these to int16
    numpy.int16: 1,
    #    numpy.int8: 1,
    # convert these to float32
    numpy.float32: 2,
    numpy.float64: 2,
    numpy.int32: 2,
    numpy.int64: 2,
    numpy.uint32: 2,
    numpy.uint64: 2,
    # convert these to complex64
    numpy.complex64: 4,
    numpy.complex128: 4,
    # convert these to uint16
    numpy.uint16: 6,
    numpy.uint8: 7,
}

intbyteorder = {
    0x11110000: 'big',
    0x44440000: 'little',  # hack
    0x44410000: 'little',
}
byteorderint = {
    'big': 0x11110000,
    'little': 0x44410000,
}
byteorderint2 = {
    'big': 286326784,
    'little': 1145110528,
}


mrc_defaults = {
    'alpha': 90,
    'beta': 90,
    'gamma': 90,
    'mapc': 1,
    'mapr': 2,
    'maps': 3,
    'map': 'MAP ',
    'byteorder': byteorderint[sys.byteorder],
}


def _gen_header():
    """Create the header for an MRC image and stack.

    .. note::

        The following code was adopted from mrc.py in Scripps Appion Package

    :Returns:

    header_image_dtype : numpy.dtype
                         Header for an MRC image
    """

    shared_fields = [
        ('nx', numpy.int32),
        ('ny', numpy.int32),
        ('nz', numpy.int32),
        ('mode', numpy.int32),
        ('nxstart', numpy.int32),
        ('nystart', numpy.int32),
        ('nzstart', numpy.int32),
        ('mx', numpy.int32),
        ('my', numpy.int32),
        ('mz', numpy.int32),
        ('xlen', numpy.float32),
        ('ylen', numpy.float32),
        ('zlen', numpy.float32),
        ('alpha', numpy.float32),  # defocus
        ('beta', numpy.float32),  # astig_ang
        ('gamma', numpy.float32),  # astig_mag
        ('mapc', numpy.int32),
        ('mapr', numpy.int32),
        ('maps', numpy.int32),
        ('amin', numpy.float32),
        ('amax', numpy.float32),
        ('amean', numpy.float32),
        ('ispg', numpy.int32),
        ('nsymbt', numpy.int32),
    ]

    header_image_dtype = numpy.dtype(
        shared_fields
        + [
            ('extra', 'S100'),
            ('xorigin', numpy.float32),  # 208 320  4   char    cmap;      Contains "MAP "
            ('yorigin', numpy.float32),
            ('zorigin', numpy.float32),
            ('map', 'S4'),
            ('byteorder', numpy.int32),
            ('rms', numpy.float32),
            ('nlabels', numpy.int32),
            ('label0', 'S80'),
            ('label1', 'S80'),  # Image Type
            # Allow image `type`s are:
            #    - Power Spectra: 'P'
            #    - Windowed Particle: 'W'
            #    - Micrograph: 'M'
            ('label2', 'S80'),
            ('label3', 'S80'),
            ('label4', 'S80'),
            ('label5', 'S80'),
            ('label6', 'S80'),
            ('label7', 'S80'),
            ('label8', 'S80'),
            ('label9', 'S80'),
        ]
    )

    return header_image_dtype


# --------------------------------------------------------------------
# End attribution
# --------------------------------------------------------------------


header_image_dtype = _gen_header()

mrc2ara = {'': ''}
mrc2ara.update({h[0]: 'mrc' + h[0] for h in header_image_dtype.names})
ara2mrc = {val: key for key, val in mrc2ara.items()}


def create_header(shape, dtype, order='C', header=None):
    """Create a header for the MRC image format.

    @todo support header parameters

    :Parameters:

    shape : tuple
            Shape of the array
    dtype : numpy.dtype
            Data type for NumPy ndarray
    header : dict
             Header values  for image
    :Returns:

    h : dtype
        Data type for NumPy ndarray describing the header
    """

    pass


def array_from_header(header):
    """Convert header information to array parameters.

    :Parameters:

    header : header_dtype
             Header fields

    :Returns:

    header : dict
             File header
    dtype : dtype
            Data type
    shape : tuple
            Shape of the array
    order : str
            Order of the array
    offset : int
             Header offset
    swap : bool
            Swap byte order
    """

    pass


def cache_data():
    """Get keywords to be added as data cache.

    :Returns:

    extra : dict
            Keyword arguments
    """

    return {'header': None, 'no_strict_mrc': False, 'force_volume': False}


def is_format_header(h):
    """Test if the given header has the proper format.

    :Parameters:

    h : array
        Header to test

    :Returns:

    val : bool
          Test if dtype matches format dtype
    """

    return h.dtype == header_image_dtype or h.dtype == header_image_dtype.newbyteorder()


bad_mrc_header = False


def is_readable(filename, no_strict_mrc=False):
    """Test if the file read has a valid MRC header.

    :Parameters:

    filename : str or file object
               Filename or open stream for a file
    no_strict_mrc : bool
                    Perform strict MRC header checking (recommended) - Only
                    EPU MRC files and Yifan's frame alignment require this
                    to be off.

    :Returns:

    out : bool
          True if the header conforms to MRC
    """

    global bad_mrc_header

    if hasattr(filename, 'dtype'):
        h = filename
        if not is_format_header(h):
            raise ValueError('Array dtype incorrect')
    else:
        try:
            h = read_mrc_header(filename)
        except BaseException:
            return False
    if _logger.isEnabledFor(logging.DEBUG):
        _logger.debug('Mode: %d - %d' % (h['mode'][0], (h['mode'][0] not in mrc2numpy)))
        _logger.debug(
            'Byteorder: %d - %d'
            % (h['byteorder'][0], ((h['byteorder'][0] & -65536) not in intbyteorder))
        )
        _logger.debug(
            'Byteorder-swap: %d - %d'
            % (
                (h['byteorder'][0].byteswap() & -65536),
                ((h['byteorder'][0].byteswap() & -65536) not in intbyteorder),
            )
        )
        for name in ('alpha', 'beta', 'gamma'):
            _logger.debug('%s: %f - %d' % (name, h[name][0], (h[name][0] != 90.0)))
        for name in ('nx', 'ny', 'nz'):
            _logger.debug('%s: %d - %d' % (name, h[name][0], (h[name][0] > 0)))
    if h['mode'][0] not in mrc2numpy:
        _logger.debug('Failed to read proper mode - not MRC!')
        return False

    if (h['byteorder'][0] & -65536) not in intbyteorder and (
        h['byteorder'][0].byteswap() & -65536
    ) not in intbyteorder:
        if (
            h['alpha'][0] == 0.0
            and h['beta'][0] == 0.0
            and h['gamma'][0] == 0.0
            and int(h['mode'][0]) == 6
        ):  # this line hack for non-standard writers
            if not bad_mrc_header:
                bad_mrc_header = True
                if not no_strict_mrc and 1 == 0:
                    _logger.warn(
                        'This image could be MRC format likely this image came from EPU. Use --no-strict-mrc to read this image'
                    )
                    return False
                _logger.warn(
                    'Assuming image is MRC format - format is not correct (Likely this image came from EPU)'
                )
        elif (
            h['alpha'][0] == 90.0 and h['beta'][0] == 90.0 and h['gamma'][0] == 90.0
        ):  # this line hack for non-standard writers
            if not bad_mrc_header:
                bad_mrc_header = True
                if not no_strict_mrc and 1 == 0:
                    _logger.warn(
                        "This image could be MRC format likely this image came from Yifan's GPU alignment. Use --no-strict-mrc to read this image"
                    )
                    return False
                _logger.warn(
                    "Assuming image is MRC format - format is not correct (Likely this image came from Yifan's GPU alignment)"
                )
        else:
            _logger.debug('Failed to read proper machine stamp - not MRC!')
            # return False
    if not numpy.all([h[v][0] > 0 for v in ('nx', 'ny', 'nz')]):
        _logger.debug('Failed to read proper dimensions - not MRC!')
        return False
    return True


def read_header(filename, index=None, no_strict_mrc=False, force_volume=False):
    """Read the MRC header.

    :Parameters:

    filename : str or file object
               Filename or open stream for a file
    index : int, ignored
            Index of image to get the header, if None, the stack header (Default: None)
    no_strict_mrc : bool
                    Perform strict MRC header checking (recommended) - Only
                    EPU MRC files and Yifan's frame alignment require this
                    to be off.
    force_volume : bool
                   Force image to be treated as a volume

    :Returns:

    header : dict
             Dictionary with header information
    """

    h = (
        read_mrc_header(filename, index, no_strict_mrc)
        if not hasattr(filename, 'ndim')
        else filename
    )
    header = {}
    header['apix'] = float(h['xlen'][0]) / float(h['nx'][0])
    header['count'] = (
        int(h['nz'][0]) if int(h['nz'][0]) != int(h['nx'][0]) and not force_volume else 1
    )
    header['nx'] = int(h['nx'][0])
    header['ny'] = int(h['ny'][0])
    header['nz'] = int(h['nz'][0]) if int(h['nz'][0]) == int(h['nx'][0]) or force_volume else 1
    for key in h.dtype.fields.keys():
        header['mrc_' + key] = h[key][0]
    header['format'] = 'mrc'
    return header


def read_mrc_header(filename, index=None, no_strict_mrc=False):
    """Read the MRC header.

    :Parameters:

    filename : str or file object
               Filename or open stream for a file
    index : int, ignored
            Index of image to get the header, if None, the stack header (Default: None)
    no_strict_mrc : bool
                    Perform strict MRC header checking (recommended) - Only
                    EPU MRC files and Yifan's frame alignment require this
                    to be off.

    :Returns:

    out : array
          Array with header information in the file
    """

    f = util.uopen(filename, 'rb')
    try:
        # curr = f.tell()
        h = util.fromfile(f, dtype=header_image_dtype, count=1)
        if not is_readable(h, no_strict_mrc):
            h = h.newbyteorder()
        if not is_readable(h, no_strict_mrc):
            raise OSError('Not MRC header')
    finally:
        util.close(filename, f)
    return h


def is_volume(filename):
    if hasattr(filename, 'dtype'):
        h = filename
    else:
        h = read_mrc_header(filename)
    return h['nz'][0] == h['nx'][0] and h['nz'][0] == h['ny'][0]


def count_images(filename, no_strict_mrc=False):
    """Count the number of images in the file.

    :Parameters:

    filename : str or file object
               Filename or open stream for a file
    no_strict_mrc : bool
                    Perform strict MRC header checking (recommended) - Only
                    EPU MRC files and Yifan's frame alignment require this
                    to be off.

    :Returns:

    out : int
          Number of images in the file
    """

    if hasattr(filename, 'dtype'):
        h = filename
    else:
        h = read_mrc_header(filename, no_strict_mrc)
    return h['nz'][0]


def iter_images(filename, index=None, header=None, no_strict_mrc=False):
    """Read a set of SPIDER images.

    :Parameters:

    filename : str or file object
               Filename or open stream for a file
    index : int, optional
            Index of image to start, if None, start with the first image (Default: None)
    header : dict, optional
             Output dictionary to place header values
    no_strict_mrc : bool
                    Perform strict MRC header checking (recommended) - Only
                    EPU MRC files and Yifan's frame alignment require this
                    to be off.

    :Returns:

    out : array
          Array with image information from the file
    """

    f = util.uopen(filename, 'rb')
    if index is None:
        index = 0
    try:
        h = read_mrc_header(f, no_strict_mrc)
        count = count_images(h)
        # if header is not None:  util.update_header(header, h, mrc2ara, 'mrc')
        tmp = read_header(h)
        if header is not None:
            header.update(tmp)
        d_len = h['nx'][0] * h['ny'][0]
        dtype = numpy.dtype(mrc2numpy[h['mode'][0]])
        offset = 1024 + int(h['nsymbt']) + 0 * d_len * dtype.itemsize
        try:
            f.seek(int(offset))
        except BaseException:
            _logger.error(f'{str(offset)} -- {str(offset.__class__.__name__)}')
            raise
        if not hasattr(index, '__iter__'):
            index = range(index, count)
        else:
            index = index.astype(numpy.int)
        last = 0
        total = file_size(f)
        if total != (
            1024
            + int(h['nsymbt'])
            + int(h['nx'][0]) * int(h['ny'][0]) * int(h['nz'][0]) * dtype.itemsize
        ):
            raise util.InvalidHeaderException(
                'file size != header: %d != %d -- %d'
                % (
                    total,
                    (
                        1024
                        + int(h['nsymbt'])
                        + int(h['nx'][0]) * int(h['ny'][0]) * int(h['nz'][0]) * dtype.itemsize
                    ),
                    int(h['nsymbt']),
                )
            )
        for i in index:
            if i != (last + 1):
                f.seek(int(1024 + int(h['nsymbt']) + i * d_len * dtype.itemsize))
            out = util.fromfile(f, dtype=dtype, count=d_len)

            out = reshape_data(out, h, index, count)
            if header_image_dtype.newbyteorder()[0] == h.dtype[0]:
                out = out.byteswap()
            yield out
    finally:
        util.close(filename, f)


def valid_image(filename, no_strict_mrc=False):
    """Test if the image is valid.

    :Parameters:

        filename : str
                   Input filename to test
        no_strict_mrc : bool
                        Perform strict MRC header checking (recommended) - Only
                        EPU MRC files and Yifan's frame alignment require this
                        to be off.

    :Returns:

        flag : bool
               True if image is valid
    """

    f = util.uopen(filename, 'rb')
    try:
        h = read_mrc_header(f, no_strict_mrc)
        total = file_size(f)
        dtype = numpy.dtype(mrc2numpy[h['mode'][0]])
        return total == (
            1024
            + int(h['nsymbt'])
            + int(h['nx'][0]) * int(h['ny'][0]) * int(h['nz'][0]) * dtype.itemsize
        )
    finally:
        util.close(filename, f)


def read_image(filename, index=None, cache=None, no_strict_mrc=False, force_volume=False):
    """Read an image from the specified file in the MRC format.

    :Parameters:

        filename : str or file object
                   Filename or open stream for a file
        index : int, optional
                Index of image to get, if None, first image (Default: None)
        no_strict_mrc : bool
                        Perform strict MRC header checking (recommended) - Only
                        EPU MRC files and Yifan's frame alignment require this
                        to be off.
        force_volume : bool
                       For image to be read as a volume

    :Returns:

        out : array
              Array with image information from the file
    """

    idx = 0 if index is None else index
    f = util.uopen(filename, 'rb')
    try:
        h = read_mrc_header(f, no_strict_mrc)
        # if header is not None: util.update_header(header, h, mrc2ara, 'mrc')
        header = read_header(h, force_volume=force_volume)
        count = count_images(h)
        if idx >= count:
            raise OSError('Index exceeds number of images in stack: %d < %d' % (idx, count))
        if index is None and (count == h['nx'][0] or force_volume):
            d_len = h['nx'][0] * h['ny'][0] * h['nz'][0]
        else:
            d_len = h['nx'][0] * h['ny'][0]
        dtype = numpy.dtype(mrc2numpy[h['mode'][0]])
        offset = 1024 + int(h['nsymbt'][0]) + idx * d_len * dtype.itemsize
        total = file_size(f)
        if total != (
            1024
            + int(h['nsymbt'][0])
            + int(h['nx'][0]) * int(h['ny'][0]) * int(h['nz'][0]) * dtype.itemsize
        ):
            raise util.InvalidHeaderException(
                'file size != header: %d != %d -- %s, %d'
                % (
                    total,
                    (
                        1024
                        + int(h['nsymbt'])
                        + int(h['nx'][0]) * int(h['ny'][0]) * int(h['nz'][0]) * dtype.itemsize
                    ),
                    str(idx),
                    int(h['nsymbt']),
                )
            )
        f.seek(int(offset))
        out = util.fromfile(f, dtype=dtype, count=d_len)
        out = reshape_data(out, h, index, count, force_volume)
        if header_image_dtype.newbyteorder()[0] == h.dtype[0]:
            out = out.byteswap()
    finally:
        util.close(filename, f)
    # assert(numpy.all(numpy.logical_not(numpy.isnan(out))))
    # if header_image_dtype.newbyteorder()==h.dtype:out = out.byteswap()
    return out, header


def reshape_data(out, h, index, count, force_volume=False):
    """Reshape the data to the proper dimensions.

    :Parameters:

    out : array
          Array with image information from the file
    h : array
        Header information
    index : int
            Index of image
    count : int
            Number of images in file

    :Returns:

    out : array
          Array with image information from the file
    """
    if index is None and int(h['nz'][0]) > 1 and (count == h['nx'][0] or force_volume):
        if h['mapc'][0] == 2 and h['mapr'][0] == 1:
            out = out.reshape((int(h['nx'][0]), int(h['ny'][0]), int(h['nz'][0])))
            for i in range(out.shape[2]):
                out[:, :, i] = out[:, :, i].squeeze().T
        else:
            out = out.reshape((int(h['nx'][0]), int(h['ny'][0]), int(h['nz'][0])))
    elif int(h['ny'][0]) > 1:
        if h['mapc'][0] == 2 and h['mapr'][0] == 1:
            out = out.reshape((int(h['ny'][0]), int(h['nx'][0])))  # .transpose() # Test this!
        else:
            out = out.reshape((int(h['ny'][0]), int(h['nx'][0])))
    return out


def file_size(fileobject):
    fileobject.seek(0, 2)  # move the cursor to the end of the file
    size = fileobject.tell()
    return size


def is_writable(filename):
    """Test if the image extension of the given filename is understood as a
    writable format.

    :Parameters:

    filename : str
               Output filename to test

    :Returns:

    write : bool
            True if the format is recognized
    """

    ext = os.path.splitext(filename)[1][1:].lower()
    return ext == 'mrc' or ext == 'ccp4' or ext == 'map'


def write_image(filename, img, index=None, header=None, inplace=False):
    """Write an image array to a file in the MRC format.

    :Parameters:

    filename : str
               Name of the output file
    img : array
          Image array
    index : int, optional
            Index to write image in the stack
    header : dict, optional
             Dictionary of header values
    inplace : bool
              Write new image to stack without removing the stack
    """

    if header is None and hasattr(img, 'header'):
        header = img.header
    try:
        img = img.astype(mrc2numpy[numpy2mrc[img.dtype.type]])
    except BaseException:
        raise TypeError(f'Unsupported type for MRC writing: {img.dtype}')

    mode = 'rb+' if index is not None and (index > 0 or inplace and index > -1) else 'wb+'
    f = util.uopen(filename, mode)
    if header is None or not hasattr(header, 'dtype') or not is_format_header(header):
        h = numpy.zeros(1, header_image_dtype)
        util.update_header(h, mrc_defaults, ara2mrc)
        pix = header.get('apix', 1.0) if header is not None else 1.0
        header = util.update_header(h, header, ara2mrc, 'mrc')
        header['nx'] = img.T.shape[0]
        header['ny'] = img.T.shape[1] if img.ndim > 1 else 1
        if header['nz'] == 0:
            header['nz'] = img.shape[2] if img.ndim > 2 else 1
        header['mode'] = numpy2mrc[img.dtype.type]
        header['mx'] = header['nx']
        header['my'] = header['ny']
        header['mz'] = header['nz']
        header['xlen'] = header['nx'] * pix
        header['ylen'] = header['ny'] * pix
        header['zlen'] = header['nz'] * pix
        header['alpha'] = 90
        header['beta'] = 90
        header['gamma'] = 90
        header['mapc'] = 1
        header['mapr'] = 2
        header['maps'] = 3
        header['amin'] = numpy.min(img)
        header['amax'] = numpy.max(img)
        header['amean'] = numpy.mean(img)

        header['map'] = 'MAP'
        header['byteorder'] = byteorderint2[sys.byteorder]  # 'DA\x00\x00'
        header['nlabels'] = 1
        header['label0'] = 'Created by Instamatic'

        # header['byteorder'] = numpy.fromstring('\x44\x41\x00\x00', dtype=header['byteorder'].dtype)

        # header['rms'] = numpy.std(img)
        if img.ndim == 3:
            header['nxstart'] = header['nx'] / -2
            header['nystart'] = header['ny'] / -2
            header['nzstart'] = header['nz'] / -2
        if index is not None:
            stack_count = index + 1
            header['nz'] = stack_count
            header['mz'] = stack_count
            header['zlen'] = stack_count
            # header['zorigin'] = stack_count/2.0
        else:
            index = 0

    try:
        if inplace:
            f.seek(
                int(1024 + int(h['nsymbt']) + index * img.ravel().shape[0] * img.dtype.itemsize)
            )
        elif f != filename:
            f.seek(0)
            header.tofile(f)
            if index > 0:
                f.seek(
                    int(
                        1024
                        + int(h['nsymbt'])
                        + index * img.ravel().shape[0] * img.dtype.itemsize
                    )
                )
        img.tofile(f)
    finally:
        util.close(filename, f)


if __name__ == '__main__':
    from pathlib import Path

    import numpy as np

    fn = Path('test.mrc')
    img = (np.random.random((512, 512)) * 100000).astype(np.uint16)

    header = {}
    header['SIZE1'] = 512
    header['SIZE2'] = 512

    write_image(fn, img, header=header)
    print('writing:', img.shape)
    print('header:', header)
    print()

    arr, h = read_image(fn)
    print('reading', arr.shape, arr.dtype)
    print('header', h)

    print()
    print('allclose:', np.allclose(img, arr))

    print(len(header_image_dtype))
