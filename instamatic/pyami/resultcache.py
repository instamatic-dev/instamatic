#!/usr/bin/env python

import weakref
import numpy
import sys

class CachedResult(object):
	def __init__(self, key, result):
		self.key = key
		self.result = result
		if isinstance(result, numpy.ndarray):
			self.size = result.size * result.itemsize
			self.result.setflags(write=False)
		else:
			self.size = sys.getsizeof(result)
		self.refcount = 0

	def __str__(self):
		return 'CachedResult(%s:%s)' % (self.key, type(self.result))

	def __repr__(self):
		return 'CachedResult(%s:%s)' % (self.key, type(self.result))

class ResultCache(object):
	def __init__(self, size_max):
		self.weakdict = weakref.WeakValueDictionary()
		self.strong_list = []
		self.strong_size_max = size_max
		self.strong_size = 0

	def getsize(self):
		return self.strong_size, len(self.strong_list)

	def getkeys(self):
		return self.weakdict.keys()

	def put(self, key, result):
		if key in self.weakdict:
			cached = self.weakdict[key]
		else:
			cached = CachedResult(key, result)
			self.weakdict[key] = cached
			self.strong_size += cached.size
			self.clean_strong()
		self.insert_strong(cached)

	def get(self, key):
		try:
			cached = self.weakdict[key]
		except:
			return None
		## this bumps it to the head of the strong list
		self.insert_strong(cached)
		return cached.result

	def insert_strong(self, cached):
		self.strong_list.insert(0, cached)
		cached.refcount += 1

	def remove_strong(self):
		cached = self.strong_list.pop()
		cached.refcount -= 1
		if cached.refcount == 0:
			self.strong_size -= cached.size

	def clean_strong(self):
		while self.strong_size > self.strong_size_max:
			self.remove_strong()

def test():
	import numpy
	cache = ResultCache(100)
	print 'KEYS', cache.weakdict.keys()

	for f in ('a', 'b', 'c', 'd', 'e', 'f', 'g', 'f', 'e', 'a'):
		a = numpy.arange(20, dtype=numpy.uint8)
		print 'PUT', f
		cache.put(f, a)
		print 'KEYS', [x.key for x in cache.strong_list]
	print ''

	for f in ('d', 'd', 'b'):
		print 'GET', f, cache.get(f)
		print 'KEYS', [x.key for x in cache.strong_list]
	print ''

	for f in ('b', 'b',):
		a = numpy.arange(20, dtype=numpy.uint8)
		print 'PUT', f
		cache.put(f, a)
		print 'KEYS', [x.key for x in cache.strong_list]
	print ''


if __name__ == '__main__':
	test()
