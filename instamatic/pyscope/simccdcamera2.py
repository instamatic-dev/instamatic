import copy
import ccdcamera
import numpy
import random
random.seed()
import time
import remote
import os
from instamatic.pyami import mrc
import itertools
from instamatic.pyscope import falconframe

FRAME_DIR = '.'

rawtype = numpy.uint32
frametype = numpy.uint8
idcounter = itertools.cycle(range(100))

has_energy_filter = False

class SimCCDCamera(ccdcamera.CCDCamera):
	name = 'SimCCDCamera'
	binning_limits = [1,2,4,8]
	binmethod = 'exact'

	def __init__(self):
		self.unsupported = []
		super(SimCCDCamera,self).__init__()
		self.pixel_size = {'x': 2.5e-5, 'y': 2.5e-5}
		self.exposure_types = ['normal', 'dark', 'bias']

		self.binning = {'x': 1, 'y': 1}
		self.offset = {'x': 0, 'y': 0}
		self.dimension = copy.copy(self.getCameraSize())
		self.exposure_time = 0.2
		self.exposure_type = 'normal'

		self.energy_filter = False
		self.energy_filter_width = 0.0

		self.views = ('square', 'empty')
		self.view = 'square'
		#self.view = 'empty'
		self.inserted = True
		if not has_energy_filter:
			self.unsupported = [
					'getEnergyFilter',
					'setEnergyFilter',
					'getEnergyFilterWidth',
					'setEnergyFilterWidth',
					'alignEnergyFilterZeroLossPeak',
			]

	def __getattribute__(self, attr_name):
		if attr_name in object.__getattribute__(self, 'unsupported'):
			raise AttributeError('attribute not supported')
		return object.__getattribute__(self, attr_name)

	def getRetractable(self):
		return True

	def getInserted(self):
		return self.inserted

	def setInserted(self, value):
		self.inserted = value

	def setView(self, view):
		self.view = view

	def getView(self):
		return self.view

	def getViews(self):
		return self.views

	def getBinnedMultiplier(self):
		binning = self.getBinning()
		return binning['x']*binning['y']

	def getBinning(self):
		return copy.copy(self.binning)

	def setBinning(self, value):
		for axis in self.binning.keys():
			try:
				if value[axis] not in self.getCameraBinnings():
					raise ValueError('invalid binning')
			except KeyError:
				pass

		for axis in self.binning.keys():
			try:
				self.binning[axis] = value[axis]
			except KeyError:
				pass

	def getOffset(self):
		return copy.copy(self.offset)

	def setOffset(self, value):
		for axis in self.offset.keys():
			try:
				if value[axis] < 0 or value[axis] >= self.getCameraSize()[axis]:
					raise ValueError('invalid offset')
			except KeyError:
				pass

		for axis in self.offset.keys():
			try:
				self.offset[axis] = value[axis]
			except KeyError:
				pass

	def getDimension(self):
		return copy.copy(self.dimension)

	def setDimension(self, value):
		for axis in self.dimension.keys():
			try:
				if value[axis] < 1 or value[axis] > self.getCameraSize()[axis]:
					raise ValueError('invalid dimension')
			except KeyError:
				pass

		for axis in self.dimension.keys():
			try:
				self.dimension[axis] = value[axis]
			except KeyError:
				pass

	def getExposureTime(self):
		return self.exposure_time*1000.0

	def setExposureTime(self, value):
		if value < 0:
			raise ValueError('invalid exposure time')
		self.exposure_time = value/1000.0

	def getExposureTypes(self):
		return self.exposure_types

	def getExposureType(self):
		return self.exposure_type

	def setExposureType(self, value):
		if value not in self.exposure_types:
			raise ValueError('invalid exposure type')
		self.exposure_type = value

	def _getImage(self):
		if not self.validateGeometry():
			raise ValueError('invalid image geometry')

		for axis in ['x', 'y']:
			if self.dimension[axis] * self.binning[axis] > self.getCameraSize()[axis]:
				raise ValueError('invalid dimension/binning combination')

		columns = self.dimension['x']
		rows = self.dimension['y']

		shape = (rows, columns)

		t0 = time.time()
		## exposure time
		time.sleep(self.exposure_time)
		t1 = time.time()
		self.exposure_timestamp = (t1 + t0) / 2.0

		return self.getSyntheticImage(shape)
	
	def getSyntheticImage(self,shape):
		dark_mean = 1.0
		bright_scale = 10
		if self.exposure_type != 'dark':
			mean = self.exposure_time * 1000.0 *bright_scale + dark_mean
			sigma = 0.01 * mean
		else:
			mean = dark_mean
			sigma = 0.1 * mean
		image = numpy.random.normal(mean, sigma, shape)
		if self.exposure_type != 'dark':
			row_offset = random.randint(-shape[0]/16, shape[0]/16) + shape[0]/4
			column_offset = random.randint(-shape[1]/16, shape[1]/16) + shape[0]/4
			image[row_offset:row_offset+shape[0]/2,
				column_offset:column_offset+shape[1]/2] += 0.5 * mean
		image = numpy.asarray(image, dtype=numpy.uint16)
		return image

	def getEnergyFiltered(self):
		return has_energy_filter

	def getEnergyFilter(self):
		return self.energy_filter

	def setEnergyFilter(self, value):
		self.energy_filter = bool(value)

	def getEnergyFilterWidth(self):
		return self.energy_filter_width

	def setEnergyFilterWidth(self, value):
		self.energy_filter_width = float(value)

	def alignEnergyFilterZeroLossPeak(self):
		pass

	def getPixelSize(self):
		return dict(self.pixel_size)

class SimFrameCamera(SimCCDCamera):
	name = 'SimFrameCamera'
	def __init__(self):
		super(SimFrameCamera,self).__init__()
		self.frame_time = 200
		self.save_frames = False
		self.alignframes = False
		self.alignfilter = 'None'
		self.rawframesname = 'frames'
		self.useframes = ()

	def _simBias(self, shape):
		bias = numpy.arange(100,115)
		bias = numpy.resize(bias, shape)
		noise = numpy.random.normal(0.0, 2.0, shape)
		bias = bias + noise
		bias = numpy.asarray(bias, rawtype)
		#print 'BIAS', bias
		return bias

	def _simDark(self, shape, exptime):
		# return image:  dark + bias
		## counts per second
		darkrate = numpy.array((0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2, 0.2), numpy.float32)
		dark = exptime * darkrate
		dark = numpy.resize(dark, shape)
		dark = dark + self._simBias(shape)
		dark = numpy.asarray(dark, rawtype)
		#print 'DARK', dark
		return dark

	def _simExposure(self, shape, exptime):
		# return image:  dark + bias + exposure
		# light sensitivity in counts per second
		sensitivity = self.binning['x'] * self.binning['y'] * numpy.arange(2000, 2065)
		sensitivity = numpy.resize(sensitivity, shape)
		exposure = exptime * sensitivity
		noise = numpy.random.normal(0.0, 50.0, shape)
		exposure = exposure + noise
		final = self._simDark(shape, exptime) + exposure
		final = numpy.asarray(final, rawtype)
		#print 'EXP', final
		return final

	def _simNormal(self, shape, exptime):
		# return image:  transparency * (dark + bias + exposure)
		final = self._simExposure(shape, exptime) * self._simSample(shape)
		final = numpy.asarray(final, rawtype)
		#print 'NORMAL', final
		return final

	def _simSample(self, shape):
		if self.view == 'empty':
			transparency = numpy.ones(shape, dtype=numpy.float32)
		elif self.view == 'square':
			transparency = 0.9 * numpy.ones(shape, dtype=numpy.float32)
			row_offset = random.randint(-shape[0]/8, shape[0]/8) + shape[0]/4
			column_offset = random.randint(-shape[1]/8, shape[1]/8) + shape[0]/4
			transparency[row_offset:row_offset+shape[0]/2,
					column_offset:column_offset+shape[1]/2] = 0.7
		#print 'VIEW', transparency
		return transparency

	def convertToInt8(self,array):
		min = 0
		max = array.max()
		array = (array / (numpy.ones(array.shape)*max))*128
		array = numpy.asarray(array,numpy.int8)
		return array

	def custom_setup(self):
		'''
		Place holder for more setup
		'''
		pass

	def _getImage(self):
		self.custom_setup()
		if not self.validateGeometry():
			raise ValueError('invalid image geometry')

		for axis in ['x', 'y']:
			if self.dimension[axis] * self.binning[axis] > self.getCameraSize()[axis]:
				raise ValueError('invalid dimension/binning combination')

		columns = self.dimension['x']
		rows = self.dimension['y']

		shape = (rows, columns)

		t0 = time.time()
		## exposure time
		time.sleep(self.exposure_time)
		t1 = time.time()
		self.exposure_timestamp = (t1 + t0) / 2.0

		nframes = self.getNumberOfFrames()
		exptime = self.frame_time

		if self.useframes:
			useframes = []
			for f in self.useframes:
				if 0 <= f < nframes:
					useframes.append(f)
		else:
			# use all frames in final image
			useframes = range(nframes)
		self.useframes = useframes

		print 'SAVERAWFRAMES', self.save_frames
		if self.save_frames:
			self.rawframesname = time.strftime('frames_%Y%m%d_%H%M%S')
			self.rawframesname += '_%02d' % (idcounter.next(),)
		else:
			return self.getSyntheticImage(shape)
		sum = numpy.zeros(shape, numpy.float32)

		for i in range(nframes):
			if self.exposure_type == 'bias':
				frame = self._simBias(shape)
			elif self.exposure_type == 'dark':
				frame = self._simDark(shape, exptime)
			elif self.exposure_type == 'normal':
				frame = self._simNormal(shape, exptime)
			else:
				raise RuntimeError('unknown exposure type: %s' % (self.exposure_type,))
			#Keep it small
			frame = self.convertToInt8(frame)

			mrcname = '.mrc'
			fname = os.path.join(FRAME_DIR,self.rawframesname + mrcname)
			if self.save_frames:
				print 'SAVE', i
				if i == 0:
					mrc.write(frame, fname)
				else:
					mrc.append(frame, fname)
			if i in self.useframes:
				print 'SUM', i
				sum += frame

		return sum

	
	def getNumberOfFrames(self):
		if self.frame_time:
			nframes = int(round(self.exposure_time / self.frame_time))
			return nframes
		else:
			return 1

	def getFrameTime(self):
		ms = self.frame_time * 1000.0
		return ms

	def setFrameTime(self,ms):
		seconds = ms / 1000.0
		self.frame_time = seconds

	def getSaveRawFrames(self):
		'''Save or Discard'''
		return self.save_frames

	def setSaveRawFrames(self, value):
		'''True: save frames,  False: discard frames'''
		self.save_frames = bool(value)

	def getAlignFrames(self):
		return self.alignframes

	def setAlignFrames(self, value):
		self.alignframes = bool(value)

	def getAlignFilter(self):
		return self.alignfilter

	def setAlignFilter(self, value):
		if value:
			self.alignfilter = str(value)
		else:
			self.alignfilter = 'None'

	def setNextRawFramesName(self, value):
		self.rawframesname = value

	def getNextRawFramesName(self):
		return self.rawframesname

	def getPreviousRawFramesName(self):
		return self.rawframesname

	def setUseFrames(self, value):
		self.useframes = value

	def getUseFrames(self):
		return self.useframes
	
class SimFalconFrameCamera(SimFrameCamera):
	name = 'SimFalconFrameCamera'
	def __init__(self):
		super(SimFalconFrameCamera,self).__init__()
		self.frameconfig = falconframe.FalconFrameConfigXmlMaker(simu=True)
		self.movie_exposure = 500.0
		self.start_frame_number = 1
		self.end_frame_number = 7
		self.equal_distr_frame_number = 0

	def getNumberOfFrames(self):
		if self.save_frames:
			return self.frameconfig.getNumberOfFrameBins()
		else:
			return 1

	def calculateMovieExposure(self):
		'''
		Movie Exposure is the exposure time to set to ConfigXmlMaker in ms
		'''
		self.movie_exposure = self.end_frame_number * self.frameconfig.getBaseFrameTime() * 1000.0
		self.frameconfig.setExposureTime(self.movie_exposure / 1000.0)

	def getReadoutDelay(self):
		'''
		Integrated image readout delay is always base_frame_time.
		There is no way to change it.
		'''
		return None

	def validateUseFramesMax(self,value):
		'''
		Return end frame number valid for the integrated image exposure time.
		'''
		if not self.save_frames:
			return 1
		# find number of frames the exposure time will give as the maximun
		self.frameconfig.setExposureTime(self.exposure_time)
		max_input_frame_value = self.frameconfig.getNumberOfAvailableFrames() - 1 
		return min(max_input_frame_value, max(value,1))

	def setUseFrames(self, frames):
		'''
		UseFrames gui for Falcon is a tuple of base_frames that defines
		the frames used in the movie.  For simplicity in input, we only
		use the min number as the movie delay and max number as the highest
		frame number to include.
		''' 
		if frames:
			if len(frames) > 1:
				self.frameconfig.setFrameReadoutDelay(min(frames))
			else:
				self.frameconfig.setFrameReadoutDelay(1)
			self.end_frame_number = self.validateUseFramesMax(max(frames))
		else:
			# default movie to start at frame 1 ( i.e., not include roll-in)
			self.frameconfig.setFrameReadoutDelay(1)
			# use impossible large number to get back value for exposure time
			self.end_frame_number = self.validateUseFramesMax(1000)
		self.start_frame_number = self.frameconfig.getFrameReadoutDelay()
		# set equally distributed frames starting frame number
		if len(frames) >2:
			framelist = list(frames)
			framelist.sort()
			self.equal_distr_frame_number = framelist[1]
		else:
			self.equal_distr_frame_number = 0
		self.frameconfig.setEquallyDistributedStartFrame(self.equal_distr_frame_number)

		self.calculateMovieExposure()
		# self.useframes is used in simulater to generate simulated sum image
		self.useframes = tuple(range(self.start_frame_number-self.frameconfig.internal_readout_delay, self.end_frame_number-self.frameconfig.internal_readout_delay))

	def getUseFrames(self):
		if self.save_frames:
			if self.equal_distr_frame_number > self.start_frame_number:
				return (self.start_frame_number,self.equal_distr_frame_number,self.end_frame_number)
			else:
				return (self.start_frame_number,self.end_frame_number)

	def setFrameTime(self,ms):
		'''
		OutputFrameTime is not detrmined by the user
		'''
		pass

	def getFrameTime(self):
		'''
		Output frame time is the average time of all frame bins.
		'''
		ms = self.movie_exposure / self.getNumberOfFrames()
		return ms

	def getPreviousRawFramesName(self):
		return self.frameconfig.getFrameDirName()

	def custom_setup(self):
		self.calculateMovieExposure()
		movie_exposure_second = self.movie_exposure/1000.0
		if self.save_frames:
			self.frameconfig.makeRealConfigFromExposureTime(movie_exposure_second,self.equal_distr_frame_number,self.start_frame_number)
		else:
			self.frameconfig.makeDummyConfig(movie_exposure_second)

class SimOtherCCDCamera(SimCCDCamera):
	name = 'SimOtherCCDCamera'
	def __init__(self):
		super(SimOtherCCDCamera,self).__init__()
		self.binning_limits = [1,2,4,8]
		self.binmethod = 'floor'

	def _getImage(self):
		im = SimCCDCamera._getImage(self)
		im = 10 * im
		return im

class SimK2CountingCamera(SimFrameCamera):
	name = 'SimK2CountingCamera'
	def __init__(self):
		super(SimK2CountingCamera,self).__init__()
		self.binning_limits = [1,2,4,8]
		self.binmethod = 'floor'

class SimK2SuperResCamera(SimFrameCamera):
	name = 'SimK2SuperResCamera'
	def __init__(self):
		super(SimK2SuperResCamera,self).__init__()
		self.binning_limits = [1]
		self.binmethod = 'floor'
