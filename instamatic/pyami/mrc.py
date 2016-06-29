#!/usr/bin/env python
'''
MRC I/O functions:
  write(a, filename, header=None)
    Write your numpy ndarray object to an MRC file.
		  a - the numpy ndarray object
      filename - the filename you want to write to
      header - (optional) dictionary of additional header information

  read(filename)
		Read MRC file into a numpy ndarray object.
      filename - the MRC filename

  mmap(filename)  
    Open MRC as a memory mapped file.  This is the most efficient way
    to read data if you only need to access part of a large MRC file.
    Only the parts you actually access are read from the disk into memory.
			filename - the MRC filename
'''

import numpy
import sys
import arraystats
import weakattr
import weakref
import resultcache
import types

cache_enabled = False
# 10 * 4kx4k float images = 640 MB
cache_size = 10 * 64 * 1024 * 1024
read_cache = resultcache.ResultCache(cache_size)

## mapping of MRC mode to numpy type
# mode 0 is defined to int8 as in MRC2010
mrc2numpy = {
	0: numpy.int8,
	1: numpy.int16,
	2: numpy.float32,
# 3 is complex made of two int16.  No such thing in numpy
#     however, we could manually build a complex array by reading two
#     int16 arrays somehow.
	4: numpy.complex64,
	5: numpy.uint8,		# UCSF Image uint8

	6: numpy.uint16,    # according to UCSF
}

# mapping of image/volume type
mrcmaptype = {
	0: 'real space',
	1: 'real space',
	2: 'real space',
	3: 'transform',
	4: 'transform',
	5: 'real space',
	6: 'real space',
}

## mapping of numpy type to MRC mode
numpy2mrc = {
	## convert these to int8
	numpy.int8: 0,
	numpy.bool: 0,
	numpy.bool_: 0,

	## convert these to int16
	numpy.int16: 1,
	numpy.uint8: 1, # Do not want to convert to mode 5

	## convert these to float32
	numpy.float32: 2,
	numpy.float64: 2,
	numpy.int32: 2,
	numpy.int64: 2,
	numpy.int: 2,
	numpy.uint32: 2,
	numpy.uint64: 2,

	## convert these to complex64
	numpy.complex: 4,
	numpy.complex64: 4,
	numpy.complex128: 4,

	## convert these to uint16
	numpy.uint16: 6,
}

## structure of the image 2000 MRC header
## This is a sequence of fields where each field is defined by a sequence:
##  (name, type, default, length)
##    length is only necessary for strings
##    type can be one of: 'int32', 'float32', 'string'
##  ** maybe look into something like http://construct.wikispaces.com/
header_fields = (
	('nx', 'int32'),
	('ny', 'int32'),
	('nz', 'int32'),
	('mode', 'int32'),
	('nxstart', 'int32'),
	('nystart', 'int32'),
	('nzstart', 'int32'),
	('mx', 'int32'),
	('my', 'int32'),
	('mz', 'int32'),
	('xlen', 'float32'),
	('ylen', 'float32'),
	('zlen', 'float32'),
	('alpha', 'float32'),
	('beta', 'float32'),
	('gamma', 'float32'),
	('mapc', 'int32'),
	('mapr', 'int32'),
	('maps', 'int32'),
	('amin', 'float32'),
	('amax', 'float32'),
	('amean', 'float32'),
	('ispg', 'int32'),
	('nsymbt', 'int32'),
	('extra1', 'string', 8),
	('exttype', 'string', 4),
	('extra2', 'string', 88),
	('xorigin', 'float32'),
	('yorigin', 'float32'),
	('zorigin', 'float32'),
	('map', 'string', 4),
	('byteorder', 'string', 4),
	('rms', 'float32'),
	('nlabels', 'int32'),
	('label0', 'string', 80),
	('label1', 'string', 80),
	('label2', 'string', 80),
	('label3', 'string', 80),
	('label4', 'string', 80),
	('label5', 'string', 80),
	('label6', 'string', 80),
	('label7', 'string', 80),
	('label8', 'string', 80),
	('label9', 'string', 80),
)

## Boulder format of stack mrc header
for i,x in enumerate(header_fields):
	if x[0] == 'extra2':
		break
header_fields_stack = list(header_fields[:i])
header_fields_stack.extend([
	("dvid", "uint16"),
	("nblank", "uint16"),
	("itst", "int32"),
	("blank", "string", 24),
	("nintegers", "uint16"),
	("nfloats", "uint16"),
	("sub", "uint16"),
	("zfac", "uint16"),
	("min2", "float32"),
	("max2", "float32"),
	("min3", "float32"),
	("max3", "float32"),
	("min4", "float32"),
	("max4", "float32"),
	("type", "uint16"),
	("lensum", "uint16"),
	("nd1", "uint16"),
	("nd2", "uint16"),
	("vd1", "uint16"),
	("vd2", "uint16"),
	("min5", "float32"),
	("max5", "float32"),
	("numtimes", "uint16"),
	("imgseq", "uint16"),
	("xtilt", "float32"),
	("ytilt", "float32"),
	("ztilt", "float32"),
	("numwaves", "uint16"),
	("wave1", "uint16"),
	("wave2", "uint16"),
	("wave3", "uint16"),
	("wave4", "uint16"),
	("wave5", "uint16"),
	("xorigin", "float32"),
	("yorigin", "float32"),
	("zorigin", "float32"),
	("nlabels", "int32"),
	('label0', 'string', 80),
	('label1', 'string', 80),
	('label2', 'string', 80),
	('label3', 'string', 80),
	('label4', 'string', 80),
	('label5', 'string', 80),
	('label6', 'string', 80),
	('label7', 'string', 80),
	('label8', 'string', 80),
	('label9', 'string', 80),
])

header_fields_extended = [
	("stagealpha", "float32"),
	("stagebeta", "float32"),
	("stagex", "float32"),
	("stagey", "float32"),
	("stagez", "float32"),
	("shiftx", "float32"),
	("shifty", "float32"),
	("defocus", "float32"),
	("exposuretime", "float32"),
	("meanintensity", "float32"),
	("tiltaxis", "float32"),
	("pixelsize", "float32"),
	("magnification", "float32"),
	("reserved", "string", 36),
]

def printHeader(headerdict):
	for field in header_fields:
		name = field[0]
		value = headerdict[name]
		print '%-10s:  %s' % (name, value)

def zeros(n):
	'''
Create n bytes of data initialized to zeros, returned as a python string.
	'''
	a = numpy.zeros(n, dtype=int8dtype)
	return a.tostring()

def newHeader(header_fields=header_fields):
	'''
Return a new initialized header dictionary.
All fields are initialized to zeros.
	'''
	header = {}
	for field in header_fields:
		name = field[0]
		type = field[1]
		if type == 'string':
			length = field[2]
			header[name] = zeros(length)
		else:
			header[name] = 0
	return header

intbyteorder = {
	'\x11\x11\x00\x00': 'big',
	'\x44\x41\x00\x00': 'little',
	'\x44\x44\x00\x00': 'little',  # compatible with badly written files
	'\x00\x00\x44\x44': 'little',  # compatible with badly written files
}
byteorderstr = {
	'big': '\x11\x11\x00\x00',
	'little': '\x44\x41\x00\x00',
}

def isSwapped(headerbytes):
	'''
Detect byte order (endianness) of MRC file based on one or more tests on
the header data.
	'''
	### check for a valid machine stamp in header, with or without byteswap
	stampswapped = None
	machstamp = headerbytes[212:216]
	machstamp = numpy.fromstring(machstamp, dtype='Int32', count=1)
	machstampint = machstamp[0]
	if machstampint in intbyteorder:
		stampswapped = False
	else:
		machstamp = machstamp.byteswap()
		machstampint = machstamp[0]
		if machstampint in intbyteorder:
			stampswapped = True

	### check for valid mode, with or without byteswap
	mode = headerbytes[12:16]
	mode = numpy.fromstring(mode, dtype='Int32', count=1)
	modeint = mode[0]
	modeswapped = None
	if modeint in mrc2numpy:
		modeswapped = False
	else:
		mode = mode.byteswap()
		modeint = mode[0]
		if modeint in mrc2numpy:
			modeswapped = True

	### final verdict on whether it is swapped
	if stampswapped is None:
		swapped = modeswapped
	elif modeswapped is None:
		swapped = stampswapped
	elif modeswapped == stampswapped:
		swapped = modeswapped
	else:
		swapped = None
	return swapped

def parseHeader(headerbytes):
	'''
	Parse the 1024 byte MRC header into a header dictionary.
	'''
	## header is comprised of Int32, Float32, and text labels.
	itype = numpy.dtype('Int32')
	ftype = numpy.dtype('Float32')

	## check if data needs to be byte swapped
	swapped = isSwapped(headerbytes)
	if swapped:
		itype = itype.newbyteorder()
		ftype = ftype.newbyteorder()

	## Convert 1k header into both floats and ints to make it easy
	## to extract all the info.
	## Only convert first 224 bytes into numbers because the
	## remainder of data are text labels
	## ** should use numpy.frombuffer or http://construct.wikispaces.com/
	headerarray = {}
	headerarray['float32'] = numpy.fromstring(headerbytes, dtype=ftype, count=224)
	headerarray['int32'] = numpy.fromstring(headerbytes, dtype=itype, count=224)

	## fill in header dictionary with all the info
	newheader = {}
	pos = 0
	for field in header_fields:
		name = field[0]
		type = field[1]
		if type == 'string':
			length = field[2]
			# remove trailing zeros(1) to make the string more readable
			full_string = headerbytes[pos:pos+length]
			first_zeros = full_string.find(zeros(1))
			newheader[name] = ''
			if first_zeros > 0:
				newheader[name] = full_string[:first_zeros]
			elif first_zeros < 0:
				newheader[name] = full_string
		else:
			length = 4
			word = pos/4
			newheader[name] = headerarray[type][word]
		pos += length

	## Save some numpy specific info (not directly related to MRC).
	## numpy dtype added to header dict because it includes both the
	## basic type (from MRC "mode") and also the byte order, which has
	## been determined independent from the byte order designation in the
	## header, which may be invalid.  This allows the data to be read
	## properly.  Also figure out the numpy shape of the data from dimensions.
	dtype = numpy.dtype(mrc2numpy[newheader['mode']])
	if swapped:
		dtype = dtype.newbyteorder()
	newheader['dtype'] = dtype
	if newheader['nz'] > 1:
		## 3D data
		shape = (newheader['nz'], newheader['ny'], newheader['nx'])
	elif newheader['ny'] > 1:
		## 2D data
		shape = (newheader['ny'], newheader['nx'])
	else:
		## 1D data
		shape = (newheader['nx'],)
	newheader['shape'] = shape

	return newheader

def updateHeaderDefaults(header):
	header['alpha'] = 90
	header['beta'] = 90
	header['gamma'] = 90
	header['mapc'] = 1
	header['mapr'] = 2
	header['maps'] = 3
	header['map'] = 'MAP '
	header['byteorder'] = byteorderstr[sys.byteorder]
	header['amin'] = 0.0
	header['amax'] = 0.0
	header['amean'] = 0.0
	header['rms'] = 0.0

def updateHeaderUsingArray(header, a, calc_stats=True, reset_origin=True, mz=None):
	'''
	Fills in values of MRC header dictionary using the given array.
	'''
	ndims = len(a.shape)
	nx = a.shape[-1]
	ny = nz = 1
	if ndims > 1:
		ny = a.shape[-2]
		if ndims > 2:
			nz = a.shape[-3]
	header['nx'] = nx
	header['ny'] = ny
	header['nz'] = nz

	mode = numpy2mrc[a.dtype.type]
	header['mode'] = mode

	if mz is None:
		mz = nz
	header['mx'] = nx
	header['my'] = ny
	header['mz'] = mz

	try:
		psize = weakattr.get(a, 'pixelsize')
	except AttributeError:
		header['xlen'] = nx
		header['ylen'] = ny
		header['zlen'] = nz
	else:
		header['xlen'] = nx * psize['x']
		header['ylen'] = ny * psize['y']
		header['zlen'] = mz * psize['x']

	if calc_stats:
		stats = arraystats.all(a)
		header['amin'] = stats['min']
		header['amax'] = stats['max']
		header['amean'] = stats['mean']
		header['rms'] = stats['std']

	if reset_origin is True:
		### changed next lines to be equivalent to proc3d origin=0,0,0
		header['xorigin'] = 0
		header['yorigin'] = 0
		header['zorigin'] = 0
	if ndims < 3:
		header['nxstart'] = 0
		header['nystart'] = 0
		header['nzstart'] = 0
	else:	
		header['nxstart'] = nx / -2
		header['nystart'] = ny / -2
		header['nzstart'] = nz / -2

int32dtype = numpy.dtype('Int32')
uint16dtype = numpy.dtype('UInt16')
float32dtype = numpy.dtype('Float32')
int8dtype = numpy.dtype('Int8')
def valueToFloat(value):
	'''
return the string representation of a float value
	'''
	a = numpy.array(value, dtype=float32dtype)
	return a.tostring()
def valueToInt(value):
	'''
return the string representation of an int value
	'''
	a = numpy.array(value, dtype=int32dtype)
	return a.tostring()
def valueToUInt16(value):
	'''
return the string representation of an int value
	'''
	a = numpy.array(value, dtype=uint16dtype)
	return a.tostring()

def makeHeaderData(h, header_fields=header_fields):
	'''
Create a 1024 byte header string from a header dictionary.
	'''
	fields = []
	for field in header_fields:
		name = field[0]
		type = field[1]
		if name in h:
			value = h[name]
		else:
			value = 0
		if type == 'string':
			length = field[2]
			s = str(value)
			nzeros = length - len(s)
			fullfield = s + zeros(nzeros)
			fields.append(fullfield)
		elif type == 'int32':
			fields.append(valueToInt(value))
		elif type == 'float32':
			fields.append(valueToFloat(value))
		elif type == 'uint16':
			fields.append(valueToUInt16(value))

	headerbytes = ''.join(fields)
	return headerbytes

def asMRCtype(a):
	'''
If necessary, convert a numpy ndarray to type that is compatible
with MRC.
	'''
	if not isinstance(a, numpy.ndarray):
		raise TypeError('Value must be a numpy array')

	t = a.dtype.type
	if t in numpy2mrc:
		numtype = t
	else:
		raise TypeError('Invalid Numeric array type for MRC conversion: %s' % (t,))
	dtype = numpy.dtype(mrc2numpy[numpy2mrc[numtype]])
	narray = numpy.asarray(a, dtype=dtype)
	return narray

def readDataFromFile(fobj, headerdict, zslice=None):
	'''
	Read data portion of MRC file from the file object fobj.
	Both mrcmode and shape have been determined from the MRC header.
	Returns a new numpy ndarray object.
	'''
	bytes_per_pixel = headerdict['dtype'].itemsize
	framesize = bytes_per_pixel * headerdict['nx'] * headerdict['ny']
	header_bytes = 1024 + headerdict['nsymbt']
	if zslice is None:
		start = header_bytes  # right after header
		shape = headerdict['shape']
	else:
		start = header_bytes + zslice * framesize
		shape = headerdict['shape'][-2:]  # only a 2-D slice
	datalen = numpy.prod(shape)
	fobj.seek(start)
	a = numpy.fromfile(fobj, dtype=headerdict['dtype'], count=datalen)
	a.shape = shape
	return a

def write(a, f, header=None, calc_stats=True, mz=None):
	'''
Write ndarray to a file
a = numpy ndarray to be written
f = MRC filename or already opened file object
header (optional) = dictionary of header parameters
Always saves in the native byte order.
	'''

	h = newHeader()
	updateHeaderDefaults(h)
	updateHeaderUsingArray(h, a, calc_stats=calc_stats, mz=mz)

	if mz is not None:
		h['mz'] = mz
		h['zlen'] = h['zlen'] * h['mz'] / h['nz']
		if h['mz'] > 1:
			if h['nz'] // h['mz'] > 1:
				h['ispg'] = 401
			else:
				h['ispg'] = 1

	if header is not None:
		h.update(header)

	headerbytes = makeHeaderData(h)
	if isinstance(f, types.StringTypes):
		fobj = open(f, 'wb')
		close = True
	elif hasattr(f, 'write'):
		fobj = f
		close = False
	else:
		raise ValueError('must supply either filename or open file-like object')
	fobj.write(headerbytes)
	appendArray(a, fobj)
	if close:
		fobj.close()

def mainStackHeader(oneheader, z):
	newheader = newHeader(header_fields=header_fields_stack)
	newheader.update(oneheader)
	newheader['nz'] = z
	newheader['mz'] = 1
	newheader['ispg'] = 0
	newheader['zlen'] = z
	newheader['zorigin'] = z/2.0
	newheader['nsymbt'] = z * 88
	newheader['exttype'] = 'IMOD'
	newheader['nintegers'] = 0
	newheader['nfloats'] = 22
	return newheader

def extendedHeader(tilt):
	newheader = {}
	newheader['stagealpha'] = tilt
	## other fields...

	return newheader

def stack(inputfiles, tilts, outputfile):
	# read first image to use as main header
	firstheader = readHeaderFromFile(inputfiles[0])
	newheader = mainStackHeader(firstheader, len(tilts))

	# mrc2014 convention
	newheader['mz'] = 1
	newheader['zlen'] = newheader['zlen'] * newheader['mz'] / newheader['nz']

	# write main header
	headerbytes = makeHeaderData(newheader, header_fields=header_fields_stack)
	f = open(outputfile, 'wb')
	f.write(headerbytes)

	# write zeros for all extended headers
	extended_length = len(tilts) * 88
	f.write(zeros(extended_length))

	# write extended headers and data
	extheaderpos = 1024
	for inputfile, tilt in zip(inputfiles, tilts):
		data = read(inputfile)

		f.seek(extheaderpos)
		extheaderpos += 88
		newheader = extendedHeader(tilt)
		headerbytes = makeHeaderData(newheader, header_fields=header_fields_extended)
		f.write(headerbytes)
		appendArray(data, f)
	f.close()

def appendArray(a, f):
	'''a = numpy array, f = open file object'''
	# make sure array is right type for MRC
	a = asMRCtype(a)

	# make sure array is in native byte order
	if not a.dtype.isnative:
		a = a.byteswap()

	# seek to end of file
	f.seek(0, 2)

	## write data in smaller chunks.  Otherwise, writing from
	## windows to a samba share will fail if image is too large.
	smallersize = 16 * 1024 * 1024
	b = a.ravel()
	items_per_write = int(smallersize / a.itemsize)
	for start in range(0, b.size, items_per_write):
		end = start + items_per_write
		b[start:end].tofile(f)

def substackFromMRCStack(mrcstack, outfile, listfile):
	''' 
	f=/path/to/stack.mrc, list=EMAN-style list, numbering starts with 0, writes output mrc stack 
	'''
	# read list, EMAN-style, one line per integer, numbersing starts with 0
	l = open(listfile, "r")
	llines = l.readlines()
	locs = [int(line.strip()) for line in llines]
	locs.sort()
	l.close()

	# get number of particles
	header = read_file_header(mrcstack)
	npart = header['shape'][0]
	print npart

	# read each individual particle and append to new mrc
	i = 0
	for loc in locs:
		if i == 0:
			a = read(mrcstack, zslice=loc)
			write(a, outfile)
		else:
			a = read(mrcstack, zslice=loc)
			append(a, outfile)
		if i % 1000 == 0:
			print "written %d images to stack" % i 
		i+=1

def invert(in_mrc, out_mrc):
	''' 
	invert an mrc image, puts image into memory, so use wisely if image is a large stack
	'''
	a = read(in_mrc)
	a = a*-1
	write(a, out_mrc)

def update_file_header(filename, headerdict):
	'''
	open the MRC header, update the fields given by headerdict
	'''
	f = open(filename, 'rb+')
	f.seek(0)
	headerbytes = f.read(1024)
	oldheader = parseHeader(headerbytes)
	oldheader.update(headerdict)
	headerbytes = makeHeaderData(oldheader)
	f.seek(0)
	f.write(headerbytes)

def read_file_header(filename):
	'''get MRC header from a file in the form of a dict'''
	f = open(filename, 'r')
	headerbytes = f.read(1024)
	header = parseHeader(headerbytes)
	return header

def append(a, filename, calc_stats=True):
	# read existing header
	f = open(filename, 'rb+')
	f.seek(0)
	headerbytes = f.read(1024)
	oldheader = parseHeader(headerbytes)

	# make a header for new array
	sliceheader = {}
	updateHeaderUsingArray(sliceheader, a, calc_stats=calc_stats)

	## check that new array is compatible with old array
	notmatch = []
	for key in ('nx', 'ny', 'mode'):
		if sliceheader[key] != oldheader[key]:
			notmatch.append(key)
	if notmatch:
		raise RuntimeError('Array to append is not compatible with existing array: %s' % (notmatch,))

	## update old header for final MRC
	oldheader['nz'] += sliceheader['nz']
	## mrc2014 convention
	if oldheader['nz'] == oldheader['mz'] and oldheader['ispg'] != 0:
		oldheader['ispg'] += 400

	## Use stats of new array.
	## In the future, maybe recalculate global stats of entire stack.
	if calc_stats:
		for key in ('amin', 'amax', 'amean', 'rms'):
			oldheader[key] = sliceheader[key]
	
	headerbytes = makeHeaderData(oldheader)
	f.seek(0)
	f.write(headerbytes)

	appendArray(a, f)

	f.close()

def readOriginFromFile(filename):
	'''
Read the X,Y,Z coordinates for the origin
	'''
	h = readHeaderFromFile(filename)
	origin = {
		'xorigin': h['xorigin'], 
		'yorigin': h['yorigin'], 
		'zorigin': h['zorigin'],
	}
	return origin

def read(filename, zslice=None):
	'''
Read the MRC file given by filename, return numpy ndarray object
	'''
	a = read_cache.get(filename)
	if a is None:
		f = open(filename, 'rb')
		headerbytes = f.read(1024)
		headerdict = parseHeader(headerbytes)
		a = readDataFromFile(f, headerdict, zslice)

		## store keep header with image
		setHeader(a, headerdict)
		## cache
		if cache_enabled:
			read_cache.put(filename, a)
	return a

def setHeader(a, headerdict):
	'''
Attach an MRC header to the array.
	'''
	weakattr.set(a, 'mrcheader', headerdict)

def getHeader(a):
	'''
Return the MRC header for the array, if it has one.
	'''
	return weakattr.get(a, 'mrcheader')

def mmap(filename):
	'''
Open filename as a memory mapped MRC file.  The returned object is
a numpy ndarray object wrapped around the memory mapped file.
	'''
	## read only the header and parse it
	headerdict = readHeaderFromFile(filename)
	headerbytes = getHeaderBytesFromFile(filename)

	## open memory mapped file
	mrcdata = numpy.memmap(filename, dtype=headerdict['dtype'], mode='r', offset=headerbytes, shape=headerdict['shape'], order='C')
	## attach header to the array
	setHeader(mrcdata, headerdict)
	return mrcdata

def getHeaderBytesFromFile(filename):
	h = readHeaderFromFile(filename)
	return h['nsymbt'] + 1024

def readHeaderFromFile(filename):
	f = open(filename)
	h = f.read(1024)
	f.close()
	h = parseHeader(h)
	return h

def sumStack(filename,dtype=numpy.float32):
	h = readHeaderFromFile(filename)
	nslices = h['nz']
	for i in range(nslices):
		if i == 0:
			a = read(filename,i)
			a.astype(dtype)
		else:
			a+= read(filename,i)
	return a

def saveSumStack(filename,outfile,dtype=numpy.float32):
	a = sumStack(filename,dtype)
	write(a, outfile)

def averageStack(filename,dtype=numpy.float32):
	h = readHeaderFromFile(filename)
	nslices = h['nz']
	for i in range(nslices):
		if i == 0:
			a = read(filename,i)
			a.astype(dtype)
		else:
			a = (a * i + read(filename,i)) / (i+1)
	return a

def saveAverageStack(filename,outfile,dtype=numpy.float32):
	a = averageStack(filename,dtype)
	write(a, outfile)

def testHeader():
	infilename = sys.argv[1]
	f = open(infilename)
	h = f.read(1024)
	f.close()
	h = parseHeader(h)
	printHeader(h)

def updateFilePixelSize(filename,pixeldict={}):
	'''
	function to update mrc header xlen so that pixel size calculated
	from xlen / nx becomes the new pixel size in Angstrom. Valid keys
	in pixeldict are 'x','y','z'.
	'''
	h = readHeaderFromFile(filename)
	for axis in pixeldict.keys():
		naxis = 'n%s' % (axis)
		axislen = '%slen' % (axis)
		h[axislen] = h[naxis] * pixeldict[axis]
	update_file_header(filename, h)


def readFilePixelSize(filename):
	'''
	function to read mrc header xlen so that pixel size calculated
	from xlen / nx becomes the new pixel size in Angstrom. Valid keys
	in pixeldict are 'x','y','z'.
	'''
	h = readHeaderFromFile(filename)
	keys = ('x', 'y', 'z',)
	pixeldict = {}
	for axis in keys:
		naxis = 'n%s' % (axis)
		axislen = '%slen' % (axis)
		pixeldict[axis] = h[axislen] / float(h[naxis])
	return pixeldict

def testWrite():
	a = numpy.zeros((16,16), numpy.float32)
	write(a, 'a.mrc')

def testStack():
	## write individual files
	files = []
	tilts = []
	for tilt in (1,2,3,4,5):
		a = tilt * numpy.ones((8,8), numpy.float32)
		filename = 'tilt%03d.mrc' % (tilt,)
		write(a, filename)
		files.append(filename)
		tilts.append(tilt)

	## make stack
	outputname = 'stack.mrc'
	stack(files, tilts, outputname)

def test_update_header():
	## read image, recalculate mean value
	a = read('test.mrc')
	newmean = a.mean()
	newheader = {'amean': newmean}
	update_file_header('test.mrc', newheader)

	## for a stack, you may not want to read the whole thing into memory
	# read header only
	h = read_file_header('test.mrc')

	# read first frame only
	a = mmap('test.mrc')
	frame = a[0]
	amin = frame.min()
	a.close()
	# read frames one at a time without using much memory
	nz = h['nz']
	for i in range(nz):
		a = mmap('test.mrc')
		frame_min = a[i].min()
		a.close()
		if frame_min < amin:
			amin = frame_min
	# update header with global min
	update_file_header('test.mrc', {'amin':amin})

def fix_file_machine_stamp(filename):
	update_file_header(filename,{'byteorder':byteorderstr[sys.byteorder]})

def appendFileLabel(filename,labelstring):
	h = readHeaderFromFile(filename)
	nlabels = h['nlabels']
	nextlabelname = 'label%d' % nlabels
	if nlabels == 10:
		raise ValueError('All labels are used')
	if h[nextlabelname]:
		raise RunTimeError('Next label indicated by NLABL is not empty')
	if len(labelstring) > 80:
		raise ValueError('Input string too long to fit in one label. Max length=80')
	update_file_header(filename,
				{'label%d' % nlabels:labelstring,'nlabels':nlabels+1})

def readAllFileLabels(filename):
	h = readHeaderFromFile(filename)
	return map((lambda x:h['label%d' % x]),range(10))

if __name__ == '__main__':
	#testHeader()
	#testWrite()
	#testStack()
	test_update_header()
