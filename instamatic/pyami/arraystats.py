#!/usr/bin/env python
'''
Functions for calculating statistics on numpy arrays.
A statistic is only calculated once on an array.  Future attempts to
calculate the statistic will return the previously calculated value.
This assumes that the values in the array are constant.  If the
array values have changed, and you want to recalculate the statistic,
then you must specify force=True.
'''

import weakattr
import numpy

debug = False
def dprint(s):
	if debug:
		print s

## publicly available functions

def min(a, force=False):
	return calc_stat(a, 'min', force)

def max(a, force=False):
	return calc_stat(a, 'max', force)

def mean(a, force=False):
	return calc_stat(a, 'mean', force)

def std(a, force=False):
	return calc_stat(a, 'std', force)

def all(a, force=False):
	return calc_stat(a, 'all', force)

def wrap_allstats(stat):
	'''
	returns a function to calculate a particular stat on an array
	'''
	if stat == 'all':
		kwargs = {'min':True,'max':True,'mean':True,'std':True}
	else:
		kwargs = {stat:True}
	def wrapped(a):
		# we cannot remove the numextension requirement here, see Bug #1105
		# which is unfortunate, because our simple mrc.py requires numextension
		try:
			import numextension
			result = numextension.allstats(a, **kwargs)
		except:
			b = numpy.asanyarray(a, dtype=numpy.float64)
			result = allstats(b, **kwargs)
		if stat != 'all':
			result = result[stat]
		return result
	return wrapped


def allstats(a, **kwargs):
	result = {
		'min': a.min(),
		'max': a.max(),
		'mean': a.mean(),
		'std': a.std(),
	}
	return result

statnames = ('min','max','mean','std')

def calc_stat(a, stat, force=False):
	'''
	Get statistic either from cache or by calculating it.
	'''
	if stat == 'all':
		need = list(statnames)
	else:
		need = [stat]
	results = {}

	## try getting it from cache
	if not force:
		for statname in list(need):
			dprint(statname)
			try:
				results[statname] = getCachedStat(a, statname)
				need.remove(statname)
			except:
				pass

	dprint('calculating: %s' % (need,))

	## calculate the rest
	if set(need) == set(statnames):
		results = wrap_allstats('all')(a)
	else:
		for statname in need:
			value = wrap_allstats(statname)(a)
			results[statname] = value

	## cache new results
	for statname in need:
		try:
			setCachedStat(a, statname, results[statname])
		except:
			pass

	if stat == 'all':
		return results
	else:
		return results[stat]

def getCachedStats(a):
	try:
		return a.stats
	except AttributeError:
		return weakattr.get(a, 'stats')

def setCachedStats(a, stats):
	try:
		a.stats = stats
	except AttributeError:
		weakattr.set(a, 'stats', stats)

def getCachedStat(a, stat):
	return getCachedStats(a)[stat]

def setCachedStat(a, stat, value):
	try:
		stats = getCachedStats(a)
	except:
		stats = {}
		setCachedStats(a, stats)
	stats[stat] = value

def test():
	import numpy
	a = numpy.array((1,2,3,4))
	print all(a)

if __name__ == '__main__':
	debug = True
	test()
