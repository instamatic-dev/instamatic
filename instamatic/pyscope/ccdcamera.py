# The Leginon software is Copyright 2004
# The Scripps Research Institute, La Jolla, CA
# For terms of the license agreement
# see http://ami.scripps.edu/software/leginon-license
#

import time
import threading
import baseinstrument
import config

class GeometryError(Exception):
	pass

class CCDCamera(baseinstrument.BaseInstrument):
	name = 'CCD Camera'
	binning_limits = [1,2,4,8]
	binmethod = 'exact'

	capabilities = baseinstrument.BaseInstrument.capabilities + (
		{'name': 'PixelSize', 'type': 'property'},
		{'name': 'Retractable', 'type': 'property'},
		{'name': 'ExposureTypes', 'type': 'property'},
		{'name': 'CameraSize', 'type': 'property'},
		{'name': 'Binning', 'type': 'property'},
		{'name': 'Dimension', 'type': 'property'},
		{'name': 'ExposureTime', 'type': 'property'},
		{'name': 'ExposureType', 'type': 'property'},
		{'name': 'Offset', 'type': 'property'},
		{'name': 'ExposureTimestamp', 'type': 'property'},
		## optional:
		{'name': 'EnergyFilter', 'type': 'property'},
		{'name': 'EnergyFilterWidth', 'type': 'property'},
		{'name': 'FrameFlip', 'type': 'property'},
		{'name': 'FrameRotate', 'type': 'property'},
	)

	def __init__(self):
		baseinstrument.BaseInstrument.__init__(self)
		self.config_name = config.getNameByClass(self.__class__)
		if self.config_name is None:
			raise RuntimeError('%s was not found in your instruments.cfg' % (self.__class__.__name__,))
		conf = config.getConfigured()[self.config_name]
		self.zplane = conf['zplane']
		if 'height' in conf and 'width' in conf:
			self.configured_size = {'x': conf['width'], 'y': conf['height']}
		else:
			self.configured_size = None
		self.buffer = {}
		self.buffer_ready = {}
		self.bufferlock = threading.Lock()
		self.readoutcallback = None
		self.callbacks = {}
		self.exposure_timestamp = None

	def getZplane(self):
		return self.zplane

	def getCameraModelName(self):
		return self.name

	def calculateCenteredGeometry(self, dimension, binning):
		camerasize = self.getCameraSize()
		offsetx = (camerasize['x']/binning - dimension)/2
		offsety = (camerasize['y']/binning - dimension)/2
		geometry = {'dimension': {'x': dimension, 'y': dimension},
								'offset': {'x': offsetx, 'y': offsety},
								'binning': {'x': binning, 'y': binning}}
		return geometry

	def validateGeometry(self, geometry=None):
		if geometry is None:
			geometry = self.getGeometry()
		camerasize = self.getCameraSize()
		for a in ['x', 'y']:
			if geometry['dimension'][a] < 0 or geometry['offset'][a] < 0:
				return False
			size = geometry['dimension'][a] + geometry['offset'][a]
			size *= geometry['binning'][a]
			if size > camerasize[a]:
				return False
		return True

	def getGeometry(self):
		geometry = {}
		geometry['dimension'] = self.getDimension()
		geometry['offset'] = self.getOffset()
		geometry['binning'] = self.getBinning()
		return geometry

	def setGeometry(self, geometry):
		if not self.validateGeometry(geometry):
			raise GeometryError
		self.setDimension(geometry['dimension'])
		self.setOffset(geometry['offset'])
		self.setBinning(geometry['binning'])

	def getSettings(self):
		settings = self.getGeometry()
		settings['exposure time'] = self.getExposureTime()
		try:
			settings['save frames'] = self.getSaveRawFrames()
		except:
			settings['save frames'] = False
		try:
			settings['frame time'] = self.getFrameTime()
		except:
			settings['frame time'] = None
		try:
			settings['use frames'] = self.getUseFrames()
		except:
			settings['use frames'] = ()
		try:
			settings['readout delay'] = self.getReadoutDelay()
		except:
			settings['readout delay'] = 0
		try:
			settings['align frames'] = self.getAlignFrames()
		except:
			settings['save frames'] = False
		try:
			settings['align frame filter'] = self.getAlignFilter()
		except:
			settings['align frame filter'] = 'None'
		return settings

	def setSettings(self, settings):
		self.setGeometry(settings)
		self.setExposureTime(settings['exposure time'])
		try:
			self.setSaveRawFrames(settings['save frames'])
		except:
			pass
		try:
			self.setUseFrames(settings['use frames'])
		except:
			pass
		try:
			self.setFrameTime(settings['frame time'])
		except:
			pass
		try:
			self.setReadoutDelay(settings['readout delay'])
		except:
			pass
		try:
			self.setAlignFrames(settings['align frames'])
		except:
			pass
		try:
			self.setAlignFilter(settings['align filter'])
		except:
			pass

	def getBinnedMultiplier(self):
		'''
Standard hardware binning causes a binned pixel to have
following:
	binned value = binning^2 * unbinned value
	OR
	unbinned value = binned value / binning^2
Sometime binning is done in software or modified in software, so there
could be a non-standard factor:
	binned value = binning^2 * unbinnned value / M
	OR
	unbinned value = M * binned value / binning^2
This method returns that multiplier, M.  In the standard case, returns 1.0.
		'''
		return 1.0

	def getBinning(self):
		raise NotImplementedError

	def setBinning(self, value):
		raise NotImplementedError

	def getOffset(self):
		raise NotImplementedError

	def setOffset(self, value):
		raise NotImplementedError

	def getDimension(self):
		raise NotImplementedError

	def setDimension(self, value):
		raise NotImplementedError

	def getExposureTime(self):
		raise NotImplementedError

	def setExposureTime(self, value):
		raise NotImplementedError

	def getExposureTypes(self):
		raise NotImplementedError

	def getExposureType(self):
		raise NotImplementedError

	def setExposureType(self, value):
		raise NotImplementedError

	def getPixelSize(self):
		raise NotImplementedError

	def getCameraBinnings(self):
		return self.binning_limits

	def getCameraBinMethod(self):
		return self.binmethod

	def getCameraSize(self):
		if self.configured_size is not None:
			return dict(self.configured_size)
		else:
			try:
				return self._getCameraSize()
			except:
				raise RuntimeError('You need to configure "width" and "height" in instruments.cfg, or implement _getCameraSize() in your camera class')

	def getExposureTimestamp(self):
		return self.exposure_timestamp

	def registerCallback(self, name, callback):
		print 'REGISTER', name, callback, time.time()
		self.callbacks[name] = callback

	def getImage(self):
		if self.readoutcallback:
			name = str(time.time())
			self.registerCallback(name, self.readoutcallback)
			self.backgroundReadout(name)
		else:
			return self._getImage()

	def setReadoutCallback(self, callback):
		self.readoutcallback = callback

	def getReadoutCallback(self):
		return None

	def backgroundReadout(self, name):
		#self.buffer_ready[name] = threading.Event()
		threading.Thread(target=self.getImageToCallback, args=(name,)).start()
		t = 0.2 + self.getExposureTime() / 1000.0
		time.sleep(t)
		## wait for t or getImage to be done, which ever is first
		#self.buffer_ready[name].wait(t)
		print 'EXPOSURE DONE (READOUT NOT DONE)', time.time()

	def getImageToCallback(self, name):
		print 'GETIMAGETOCALLBACK', name, time.time()
		image = self._getImage()
		try:
			print 'CALLBACK', self.callbacks[name], time.time()
			self.callbacks[name](image)
			print 'CALLBACKDONE', time.time()
		finally:
			del self.callbacks[name]

	def getImageToBuffer(self, name):
		image = self._getImage()
		self.bufferlock.acquire()
		self.buffer[name] = image
		self.bufferlock.release()
		self.buffer_ready[name].set()

	def getBuffer(self, name, block=True):
		if block:
			self.buffer_ready[name].wait()
		self.bufferlock.acquire()
		if name in self.buffer:
			image = self.buffer[name]
			del self.buffer[name]
			del self.buffer_ready[name]
		else:	
			image = None
		self.bufferlock.release()
		return image

	def _getImage(self):
		raise NotImplementedError

	def getRetractable(self):
		return False

	def getEnergyFiltered(self):
		return False

	def getSaveRawFrames(self):
		return False

	def getNumberOfFrames(self):
		return 1
	#def setSaveRawFrames(self, value):
	#	raise NotImplementedError

	def getAlignFrames(self):
		return False

	#def setAlignFrames(self, value):
	#	raise NotImplementedError

	def getAlignFilter(self):
		return 'None'

	#def setAlignFilter(self, value):
	#	raise NotImplementedError

	def getSystemGainDarkCorrected(self):
		return False

	def getFrameFlip(self):
		# flip before? rotation
		return False

	def getFrameRotate(self):
		# rotation in multiple of 90 degrees
		return 0
