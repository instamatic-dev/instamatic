#!/usr/bin/env python
'''
Defines the pyscope server and client protocol.
Data are converted to pickles and passed over socket.

Test procedure:
This is a self contained executable python script.  It can start either
a server or a client.  To start a server, run the following command line:
	remote.py server
To start client:
	remote.py client login host
In these test cases, port number is fixed: 55555
'''

import SocketServer
import socket
import config
import cPickle
import instamatic.pyscope.tem
import instamatic.pyscope.ccdcamera
import traceback

PYSCOPE_PORT = 55555

class PyscopeData(object):
	'''Base class for all data passed between client and server'''
	def __init__(self):
		self.login = None

class LoginRequest(PyscopeData):
	'''request login to a pyscope server'''
	def __init__(self, status):
		PyscopeData.__init__(self)
		self.status = status

class LoginResponse(PyscopeData):
	'''server response to client login request'''
	def __init__(self, status):
		PyscopeData.__init__(self)
		self.status = status

class UnauthorizedRequest(PyscopeData):
	'''Response to an unauthorized request'''
	def __init__(self, reason):
		PyscopeData.__init__(self)
		self.reason = reason

class CapabilityRequest(PyscopeData):
	'''request the set of capabilities provided by server'''
	pass

class CapabilityResponse(PyscopeData, dict):
	'''response with set of capabilities provided by server'''
	def __init__(self, initializer={}):
		PyscopeData.__init__(self)
		dict.__init__(self, initializer)

class InstrumentData(PyscopeData):
	'Base class for instrument specific data'
	def __init__(self, instrument):
		PyscopeData.__init__(self)
		self.instrument = instrument

class GetRequest(list, InstrumentData):
	def __init__(self, instrument, sequence=[]):
		list.__init__(self, sequence)
		InstrumentData.__init__(self, instrument)

class GetResponse(dict, InstrumentData):
	def __init__(self, instrument, initializer={}):
		dict.__init__(self, initializer)
		InstrumentData.__init__(self, instrument)

class SetRequest(dict, InstrumentData):
	def __init__(self, instrument, initializer={}):
		dict.__init__(self, initializer)
		InstrumentData.__init__(self, instrument)

class SetResponse(dict, InstrumentData):
	def __init__(self, instrument, initializer={}):
		dict.__init__(self, initializer)
		InstrumentData.__init__(self, instrument)

class CallRequest(InstrumentData):
	def __init__(self, instrument, method, *args, **kwargs):
		InstrumentData.__init__(self, instrument)
		self.method = method
		self.args = args
		self.kwargs = kwargs

class CallResponse(InstrumentData):
	def __init__(self, instrument, result):
		InstrumentData.__init__(self, instrument)
		self.result = result

class PickleHandler(object):
	'define self.rfile and self.wfile in subclass'
	def readObject(self):
		obj = cPickle.load(self.rfile)
		return obj

	def writeObject(self, obj):
		cPickle.dump(obj, self.wfile)
		self.wfile.flush()

class PickleRequestHandler(SocketServer.StreamRequestHandler, PickleHandler):
	def handle(self):
		request_object = self.readObject()
		response_object = self.handle_object(request_object)
		self.writeObject(response_object)

	def handle_object(self, object):
		raise NotImplementedError('define handle_object in subclass')

class HandlerError(Exception):
	def __init__(self):
		## traceback cannot be pickled, so convert to string
		info = '######### Server traceback:\n%s########### End server traceback\n' % (traceback.format_exc(),)
		Exception.__init__(self, info)

class InstrumentRequestHandler(PickleRequestHandler):
	def setup(self):
		PickleRequestHandler.setup(self)
		self.instruments = self.server.instruments

	def handle_object(self, request):
		if isinstance(request, LoginRequest):
			return self.handle_login(request)

		status = self.getClientStatus(request.login)
		if status is None:
			return self.handle_unauthorized(request, 'not logged in')

		## any loged in client can make these requests
		if isinstance(request, GetRequest):
			return self.handle_get(request)
		if isinstance(request, CapabilityRequest):
			return self.handle_capability(request)

		if status != 'controller':
			return self.handle_unauthorized(request, 'not controller')

		## controllers only past this point
		if isinstance(request, SetRequest):
			return self.handle_set(request)
		if isinstance(request, CallRequest):
			return self.handle_call(request)

	def getClientStatus(self, login):
		if login in self.server.clients:
			return self.server.clients[login]['status']
		else:
			return None

	def handle_unauthorized(self, request, reason):
		response = UnauthorizedRequest(reason=reason)
		return response

	def handle_login(self, request):
		server_clients = self.server.clients
		login = request.login
		newstatus = request.status
		if login in server_clients:
			oldstatus = server_clients[login]['status']
		else:
			oldstatus = None

		old_controller = self.server.controller
		new_controller = None

		## The following cases reject requested status
		if newstatus not in ('controller', 'observer', 'logout'):
			print 'REJECT', login, newstatus
			## unknown status
			newstatus = oldstatus
		elif newstatus == 'controller' and old_controller is not None:
			print 'REJECT', login, newstatus
			## reject controller request if already have a controller
			newstatus = oldstatus

		## The following cases update server.controller if necessary
		if newstatus == 'controller':
			## New controller
			self.server.controller = login
			print 'NEW CONTROLLER', login
		elif oldstatus == 'controller':
			## Was controller, but not anymore
			self.server.controller = None
			print 'QUIT CONTROLLER', login

		## update server.clients and generate response
		if newstatus == 'logout':
			if login in server_clients:
				del server_clients[login]
			print 'LOGOUT', login
		else:
			if login not in server_clients:
				server_clients[login] = {}
			server_clients[login]['status'] = newstatus
			print 'STATUS', login, newstatus
		response = LoginResponse(status=newstatus)
		return response

	def handle_capability(self, request):
		caps = self.instruments.getCapabilities()
		response = CapabilityResponse()
		response.update(caps)
		return response

	def handle_get(self, request):
		instrument = self.instruments[request.instrument]
		response = GetResponse(request.instrument)
		for name in request:
			attr = 'get' + name
			try:
				func = getattr(instrument, attr)
				response[name] = func()
			except:
				response[name] = HandlerError()
		return response

	def handle_set(self, request):
		instrument = self.instruments[request.instrument]
		response = SetResponse(request.instrument)
		for name, value in request.items():
			attr = 'set' + name
			try:
				func = getattr(instrument, attr)
				response[name] = func(value)
			except:
				response[name] = HandlerError()
		return response

	def handle_call(self, request):
		instrument = self.instruments[request.instrument]
		attr = request.method
		args = request.args
		kwargs = request.kwargs
		try:
			func = getattr(instrument, attr)
			result = func(*args, **kwargs)
		except:
			result = HandlerError()
		response = CallResponse(request.instrument, result)

class Server(SocketServer.TCPServer):
	allow_reuse_address = True
	def __init__(self, *args, **kwargs):
		SocketServer.TCPServer.__init__(self, *args, **kwargs)
		self.instruments = Instruments()
		self.clients = {}
		self.controller = None

class Instruments(dict):
	'''This instantiates all configured instruments'''
	def __init__(self):
		dict.__init__(self)
		for name,cls in config.getConfigured().items():
			self[name] = cls()

	def getCapabilities(self):
		caps = {}
		for name, instrument in self.items():
			caps[name] = {}
			if isinstance(instrument, instamatic.pyscope.tem.TEM):
				inst_type = 'TEM'
			elif isinstance(instrument, instamatic.pyscope.ccdcamera.CCDCamera):
				inst_type = 'CCDCamera'
			caps[name]['type'] = inst_type
			caps[name]['caps'] = instrument.getCapabilities()
		return caps

class Client(PickleHandler):
	def __init__(self, login, status, host='', port=PYSCOPE_PORT):
		self.login = login
		self.host = host
		self.port = port
		self.doLogin(status)

	def __del__(self):
		try:
			self.logout()
			PickleHandler.__del__(self)
		except:
			pass

	def connect(self):
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((self.host, self.port))
		self.wfile = s.makefile('wb')
		self.rfile = s.makefile('rb')

	def disconnect(self):
		self.wfile.close()
		self.rfile.close()

	def doRequest(self, request):
		request.login = self.login
		self.connect()
		self.writeObject(request)
		response = self.readObject()
		self.disconnect()
		return response

	def doLogin(self, status):
		req = LoginRequest(status)
		response = self.doRequest(req)
		if response.status != status:
			raise Exception('unable to log in with status "%s"' % (status,))

	def logout(self):
		req = LoginRequest('logout')
		response = self.doRequest(req)
		if response.status != req.status:
			print 'AAAAAAAAAAAAAAAAA'
			raise Exception('unable to log out')

	def getCapabilities(self):
		req = CapabilityRequest()
		caps = self.doRequest(req)
		return caps

	def set(self, instrument, property_dict):
		req = SetRequest(instrument, property_dict)
		response = self.doRequest(req)
		return response

	def get(self, instrument, property_list):
		req = GetRequest(instrument, property_list)
		response = self.doRequest(req)
		return response

	def call(self, instrument, method, *args, **kwargs):
		req = CallRequest(instrument, method, *args, **kwargs)
		response = self.doRequest(req)
		return response


def startServer():
	addr = ('', PYSCOPE_PORT)
	server = Server(addr, InstrumentRequestHandler)
	server.serve_forever()

if __name__ == '__main__':
	import sys
	if sys.argv[1] == 'server':
		startServer()
	elif sys.argv[1] == 'client':
		login = sys.argv[2]
		status = sys.argv[3]
		if len(sys.argv) == 5:
			host = sys.argv[4]
		else:
			host = ''
		c = Client(login, status, host)
		print ''
		print c.getCapabilities()
		print ''
		print c.set('Sim TEM', {'StagePosition': {'x':0.0005}})
		print ''
		print c.get('Sim TEM', ['StagePosition'])
		print ''
		print c.get('Sim TEM', ['StagePosition','SpotSize','dummy'])
		print ''
		print c.call('Sim TEM', 'resetDefocus')
		print ''
		import time
		time.sleep(2)
