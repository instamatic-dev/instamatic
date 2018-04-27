import socket
import pickle
import time
import atexit
from functools import partial
import subprocess as sp
from itertools import chain


HOST = 'localhost'
PORT = 8088


class CommunicationError(Exception):
    pass


def kill_server(p):
    # p.kill is not adequate
    sp.call(['taskkill', '/F', '/T', '/PID',  str(p.pid)])


def start_server_in_subprocess():
   cmd = "instamatic.temserver.exe"
   p = sp.Popen(cmd)
   print(f"Starting TEM server server ({HOST}:{PORT} on pid={p.pid})")
   atexit.register(kill_server, p)


class ServerMicroscope(object):
    """docstring for microscope"""
    def __init__(self, name):
        super().__init__()
        
        self.name = name
        
        try:
            self.connect()
        except ConnectionRefusedError:
            start_server_in_subprocess()

            for t in range(30):
                try:
                    self.connect()
                except ConnectionRefusedError:
                    time.sleep(1)
                    if t > 3:
                        print("Waiting for server")
                    if t > 30:
                        raise RuntimeError("Cannot establish server connection (timeout)")
                else:
                    break

        atexit.register(self.s.close)
    
    def connect(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((HOST, PORT))
        print(f"Connected to server ({HOST}:{PORT})")

    def __getattr__(self, name):
        self.t0 = time.clock()
        return partial(self._func, name)

    def _func(self, name, *args, **kwargs):
        c = chain((repr(arg) for arg in args), (f'{k}={repr(v)}' for k,v in kwargs.items()))
        cmd = f"tem.{name}({', '.join(c)})"
        return self._eval(cmd)

    def _eval(self, cmd):
        # t0 = time.clock()
        # t0 = self.t0

        # print(cmd)

        self.s.send(cmd.encode())
        data = self.s.recv(1024)
        if data:
            data = pickle.loads(data)

        if isinstance(data, str) and data.startswith("error"):
            raise CommunicationError(data)
       
        # t1 = time.clock()
        # print(f"{1000*(t1-t0):.2f} ms")
        # print(data)

        return data

    # def getBrightness(self):
    #     cmd = f"tem.getBrightness()"
    #     return self._eval(cmd)

    # def setBrightness(self, value):
    #     cmd = f"tem.setBrightness(value={value})"
    #     return self._eval(cmd)
    
    # def getMagnification(self):
    #     cmd = f"tem.getMagnification()"
    #     return self._eval(cmd)

    # def setMagnification(self, value):
    #     cmd = f"tem.setMagnification(value={value})"
    #     return self._eval(cmd)

    # def getMagnificationIndex(self):
    #     cmd = f"tem.getMagnificationIndex()"
    #     return self._eval(cmd)

    # def setMagnificationIndex(self, index):
    #     cmd = f"tem.setMagnificationIndex(index={index})"
    #     return self._eval(cmd)

    # def getGunShift(self):
    #     cmd = f"tem.getGunShift()"
    #     return self._eval(cmd)

    # def setGunShift(self, x, y):
    #     cmd = f"tem.setGunShift(x={x}, y={y})"
    #     return self._eval(cmd)
    
    # def getGunTilt(self):
    #     cmd = f"tem.getGunTilt()"
    #     return self._eval(cmd)
    
    # def setGunTilt(self, x, y):
    #     cmd = f"tem.setGunTilt(x={x}, y={y})"
    #     return self._eval(cmd)

    # def getBeamShift(self):
    #     cmd = f"tem.getBeamShift()"
    #     return self._eval(cmd)

    # def setBeamShift(self, x, y):
    #     cmd = f"tem.setBeamShift(x={x}, y={y})"
    #     return self._eval(cmd)

    # def getBeamTilt(self):
    #     cmd = f"tem.getBeamTilt()"
    #     return self._eval(cmd)
    
    # def setBeamTilt(self, x, y):
    #     cmd = f"tem.setBeamTilt(x={x}, y={y})"
    #     return self._eval(cmd)

    # def getImageShift1(self):
    #     cmd = f"tem.getImageShift1()"
    #     return self._eval(cmd)

    # def setImageShift1(self, x, y):
    #     cmd = f"tem.setImageShift1(x={x}, y={y})"
    #     return self._eval(cmd)

    # def getImageShift2(self):
    #     cmd = f"tem.getImageShift2()"
    #     return self._eval(cmd)

    # def setImageShift2(self, x, y):
    #     cmd = f"tem.setImageShift2(x={x}, y={y})"
    #     return self._eval(cmd)

    # def getStagePosition(self):
    #     cmd = f"tem.getStagePosition()"
    #     return self._eval(cmd)

    # def isStageMoving(self):
    #     cmd = f"tem.isStageMoving()"
    #     return self._eval(cmd)

    # def waitForStage(self, delay=0.1):
    #     cmd = f"tem.waitForStage(delay={delay})"
    #     return self._eval(cmd)

    # def setStageX(self, value, wait=True):
    #     cmd = f"tem.setStageX(value={value}, wait={wait})"
    #     return self._eval(cmd)

    # def setStageY(self, value, wait=True):
    #     cmd = f"tem.setStageY(value={value}, wait={wait})"
    #     return self._eval(cmd)

    # def setStageZ(self, value, wait=True):
    #     cmd = f"tem.setStageZ(value={value}, wait={wait})"
    #     return self._eval(cmd)

    # def setStageA(self, value, wait=True):
    #     cmd = f"tem.setStageA(value={value}, wait={wait})"
    #     return self._eval(cmd)

    # def setStageB(self, value, wait=True):
    #     cmd = f"tem.setStageB(value={value}, wait={wait})"
    #     return self._eval(cmd)

    # def setStageXY(self, x, y, wait=True):
    #     cmd = f"tem.setStageXY(x={x}, y={y}, wait={wait})"
    #     return self._eval(cmd)

    # def stopStage(self):
    #     cmd = f"tem.stopStage()"
    #     return self._eval(cmd)

    # def setStagePosition(self, x=None, y=None, z=None, a=None, b=None, wait=True):
    #     cmd = f"tem.setStagePosition(x={x}, y={y}, z={z}, a={a}, b={b}, wait={wait})"
    #     return self._eval(cmd)

    # def getFunctionMode(self):
    #     cmd = f"tem.getFunctionMode()"
    #     return self._eval(cmd)

    # def setFunctionMode(self, value):
    #     cmd = f"tem.setFunctionMode(value={value})"
    #     return self._eval(cmd)

    # def getDiffFocus(self):
    #     cmd = f"tem.getDiffFocus()"
    #     return self._eval(cmd)

    # def setDiffFocus(self, value):
    #     cmd = f"tem.setDiffFocus(value={value})"
    #     return self._eval(cmd)

    # def getDiffShift(self):
    #     cmd = f"tem.getDiffShift()"
    #     return self._eval(cmd)

    # def setDiffShift(self, x, y):
    #     cmd = f"tem.setDiffShift(x={x}, y={y})"
    #     return self._eval(cmd)

    # def isBeamBlanked(self, value):
    #     cmd = f"tem.isBeamBlanked(value={value})"
    #     return self._eval(cmd)

    # def setBeamBlank(self, mode):
    #     cmd = f"tem.setBeamBlank(mode={mode})"
    #     return self._eval(cmd)

    # def getCondensorLensStigmator(self):
    #     cmd = f"tem.getCondensorLensStigmator()"
    #     return self._eval(cmd)

    # def setCondensorLensStigmator(self, x, y):
    #     cmd = f"tem.setCondensorLensStigmator(x={x}, y={y})"
    #     return self._eval(cmd)
        
    # def getIntermediateLensStigmator(self):
    #     cmd = f"tem.getIntermediateLensStigmator()"
    #     return self._eval(cmd)

    # def setIntermediateLensStigmator(self, x, y):
    #     cmd = f"tem.setIntermediateLensStigmator(x={x}, y={y})"
    #     return self._eval(cmd)

    # def getObjectiveLensStigmator(self):
    #     cmd = f"tem.getObjectiveLensStigmator()"
    #     return self._eval(cmd)

    # def setObjectiveLensStigmator(self, x, y):
    #     cmd = f"tem.setObjectiveLensStigmator(x={x}, y={y})"
    #     return self._eval(cmd)

    # def getSpotSize(self):
    #     cmd = f"tem.getSpotSize()"
    #     return self._eval(cmd)

    # def getScreenPosition(self):
    #     cmd = f"tem.getScreenPosition()"
    #     return self._eval(cmd)

    # def setScreenPosition(self, value):
    #     cmd = f"tem.setScreenPosition(value={value})"
    #     return self._eval(cmd)

    # def setSpotSize(self, value):
    #     cmd = f"tem.setSpotSize(value={value})"
    #     return self._eval(cmd)

    # def getCondensorLens1(self):
    #     cmd = f"tem.getCondensorLens1()"
    #     return self._eval(cmd)

    # def getCondensorLens2(self):
    #     cmd = f"tem.getCondensorLens2()"
    #     return self._eval(cmd)

    # def getCondensorMiniLens(self):
    #     cmd = f"tem.getCondensorMiniLens()"
    #     return self._eval(cmd)

    # def getObjectiveLenseCoarse(self):
    #     cmd = f"tem.getObjectiveLenseCoarse()"
    #     return self._eval(cmd)

    # def getObjectiveLenseFine(self):
    #     cmd = f"tem.getObjectiveLenseFine()"
    #     return self._eval(cmd)
    
    # def getObjectiveMiniLens(self):
    #     cmd = f"tem.getObjectiveMiniLens()"
    #     return self._eval(cmd)