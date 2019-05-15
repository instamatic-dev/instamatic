import numpy as np

# from https://github.com/silx-kit/fabio/blob/master/fabio/adscimage.py


def swap_needed(header: dict) -> bool:
    if "BYTE_ORDER" not in header:
        # logger.warning("No byte order specified, assuming little_endian")
        BYTE_ORDER = "little_endian"
    else:
        BYTE_ORDER = header["BYTE_ORDER"]
    if "little" in BYTE_ORDER and np.little_endian:
        return False
    elif "big" in BYTE_ORDER and not np.little_endian:
        return False
    elif  "little" in BYTE_ORDER and not np.little_endian:
        return True
    elif  "big" in BYTE_ORDER and np.little_endian:
        return True


def write_adsc(fname: str, data: np.array, header: dict={}):
    """
    Write adsc format
    """
    out = b'{\n'
    for key in header:
        out += "{:}={:};\n".format(key, header[key]).encode()
    if "HEADER_BYTES" in header:
        pad = int(header["HEADER_BYTES"]) - len(out) - 2
    else:
#         hsize = ((len(out) + 23) // 512 + 1) * 512
        hsize = (len(out) + 533) & ~(512 - 1)
        out += "HEADER_BYTES={:d};\n".format(hsize).encode()
        pad = hsize - len(out) - 2
    out +=  b"}" + (pad+1) * b'\x00' 
    assert len(out) % 512 == 0 , "Header is not multiple of 512"

    # NOTE: XDS can handle only "SMV" images of TYPE=unsigned_short.
    dtype = np.uint16
    data = np.round(data, 0).astype(dtype, copy=False)  # copy=False ensures that no copy is made if dtype is already satisfied
    if swap_needed(header):
        data.byteswap(True)

    with open(fname, "wb") as outf:
        outf.write(out)
        outf.write(data.tostring())


def readheader(infile):
    """ read an adsc header """
    header = {}
    line = infile.readline()
    bytesread = len(line)
    while b'}' not in line:
        string = line.decode().strip()
        if '=' in string:
            (key, val) = string.split('=')
            val = val.strip(';')
            key = key.strip()
            header[key] = val
        line = infile.readline()
        bytesread = bytesread + len(line)
    return header


def read_adsc(fname: str) -> (np.array, dict):
    """ read in the file """
    with open(fname, "rb", buffering=0) as infile:
        try:
            header = readheader(infile)
        except:
            raise Exception("Error processing adsc header")
        # banned by bzip/gzip???
        try:
            infile.seek(int(header['HEADER_BYTES']), 0)
        except TypeError:
            # Gzipped does not allow a seek and read header is not
            # promising to stop in the right place
            infile.close()
            infile = open(fname, "rb", buffering=0)
            infile.read(int(header['HEADER_BYTES']))
        binary = infile.read()
    # infile.close()

    # now read the data into the array
    dim1 = int(header['SIZE1'])
    dim2 = int(header['SIZE2'])
    data = np.fromstring(binary, np.uint16)
    if swap_needed(header):
        data.byteswap(True)
    try:
        data.shape = (dim2, dim1)
    except ValueError:
            raise IOError('Size spec in ADSC-header does not match ' + \
                          'size of image data field %sx%s != %s' % (dim1, dim2, data.size))
    
    return data, header


if __name__ == '__main__':
    fn = "test.img"
    img = (np.random.random((512, 512)) * 100000).astype(np.uint16)

    header = {}
    header['SIZE1'] = 512
    header['SIZE2'] = 512
    
    write_adsc(fn, img, header=header)
    print("writing:", img.shape)
    print("header:", header)
    print()

    arr,h = read_adsc(fn)
    print("reading", arr.shape)
    print("header", h)
    
    print()
    print("allclose:", np.allclose(img, arr))
