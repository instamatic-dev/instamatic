r"""## gatansocket3.py.

`gatansocket3.py` defines a client class to interface with the socket based DM plugin.

The script adapted from [Leginon](http://emg.nysbc.org/redmine/projects/leginon/wiki/Leginon_Homepage). Leginon is licenced under the Apache License, Version 2.0. The code (`gatansocket3.py`) was converted from Python2.7 to Python3.6+ from [here](http://emg.nysbc.org/redmine/projects/leginon/repository/revisions/trunk/entry/pyscope/gatansocket.py).

It needs the SERIALEMCCD plugin to be installed in DigitalMicrograph. The relevant instructions from the [SerialEM documentation](https://bio3d.colorado.edu/SerialEM/hlp/html/setting_up_serialem.htm) are referenced below.

### Setup [1]

To connect to DigitalMicrograph through a socket interface on the same or a different computer, such as for a K2/K3 camera with SerialEM running on an FEI microscope, you need to do the following:
 - Determine the IP address of the computer running DM on the network which that computer shares with the computer running SerialEM.  If SerialEM and DM are running on the same computer, use `127.0.0.1` for the address.
 - Copy the appropriate SerialEMCDD plugin from the SerialEM_3-x-x folder to a Plugins folder on the other computer (the one running DM). Specifically:
     - If the other computer is running 64-bit Windows, copy  `SEMCCD-GMS2.31-64.dll`, `SEMCCD-GMS3.30-64.dll`, or `SEMCCD-GMS3.31-64.dll` to `C:\ProgramData\Gatan\Plugins` and rename it to `SEMCCD-GMS2-64.dll`
     - If the other computer is running GMS2 on Windows XP or Windows 7 32-bit, copy `SEMCCD-GMS2.0-32.dll` or `SEMCCD-GMS2.3-32.dll` to `C:\Program Files\Gatan\Plugins` and rename it to `SEMCCD-GMS2-32.dll`
     - If the other computer is running GMS 1, copy `SerialEMCCD.dll` to `C:\Program Files\Gatan\DigitalMicrograph\Plugins`
 - If DM and SerialEM are running on the same computer, the installer should have placed the right plugin in the right folder, but if not, follow the procedure just given.
 - On the computer running DM, define a system environment variable `SERIALEMCCD_PORT` with the value `48890` or other selected port number, as described in the section above.
 - Make sure that this port is open for communication between SerialEM and DM. If there is any possibility of either machine being exposed to the internet, do not simply turn off the firewalls; open only this specific port in the firewall, and allow access only by the other machine or the local subnet.  Even if just this one port is exposed to the world, port scanners can interfere with communication and DM function.
 - Restart DM. Note that no registration is needed for the plugin when using a socket interface.
 - If the connection does not work, debugging output can be obtained on both sides by:
     - Setting an environment variable `SERIALEMCCD_DEBUG` with the value of `1` or `2`, where `2` will give more verbose output related to the socket operations.

[1]. https://bio3d.colorado.edu/SerialEM/hlp/html/setting_up_serialem.htm
"""

from __future__ import annotations

import os
import socket
import time

import numpy as np

# set this to a file name to log some socket debug messages.
# Set to None to avoid saving a log.
# for example:
debug_log = None
# debug_log = 'gatansocket.log'

# enum function codes as in GatanSocket.cpp and SocketPathway.cpp
# need to match exactly both in number and order
enum_gs = [
    'GS_ExecuteScript',
    'GS_SetDebugMode',
    'GS_SetDMVersion',
    'GS_SetCurrentCamera',
    'GS_QueueScript',
    'GS_GetAcquiredImage',
    'GS_GetDarkReference',
    'GS_GetGainReference',
    'GS_SelectCamera',
    'GS_SetReadMode',
    'GS_GetNumberOfCameras',
    'GS_IsCameraInserted',
    'GS_InsertCamera',
    'GS_GetDMVersion',
    'GS_GetDMCapabilities',
    'GS_SetShutterNormallyClosed',
    'GS_SetNoDMSettling',
    'GS_GetDSProperties',
    'GS_AcquireDSImage',
    'GS_ReturnDSChannel',
    'GS_StopDSAcquisition',
    'GS_CheckReferenceTime',
    'GS_SetK2Parameters',
    'GS_ChunkHandshake',
    'GS_SetupFileSaving',
    'GS_GetFileSaveResult',
    'GS_SetupFileSaving2',
    'GS_GetDefectList',
    'GS_SetK2Parameters2',
    'GS_StopContinuousCamera',
    'GS_GetPluginVersion',
    'GS_GetLastError',
    'GS_FreeK2GainReference',
]
# lookup table of function name to function code, starting with 1
enum_gs = {x: y for (y, x) in enumerate(enum_gs, 1)}

# C "long" -> numpy "int_"
ARGS_BUFFER_SIZE = 1024
MAX_LONG_ARGS = 16
MAX_DBL_ARGS = 8
MAX_BOOL_ARGS = 8
sArgsBuffer = np.zeros(ARGS_BUFFER_SIZE, dtype=np.byte)


class Message:
    """Information packet to send and receive on the socket.

    Initialize with the sequences of args (longs, bools, doubles) and
    optional long array.
    """

    def __init__(self, longargs=[], boolargs=[], dblargs=[], longarray=[]):
        # Strings are packaged as long array using np.frombuffer(buffer,np.int_)
        # and can be converted back with longarray.tobytes()
        # add final longarg with size of the longarray
        if len(longarray):
            longargs = list(longargs)
            longargs.append(len(longarray))

        self.dtype = [
            ('size', np.intc),
            ('longargs', np.int_, (len(longargs),)),
            ('boolargs', np.int32, (len(boolargs),)),
            ('dblargs', np.double, (len(dblargs),)),
            ('longarray', np.int_, (len(longarray),)),
        ]
        self.array = np.zeros((), dtype=self.dtype)
        self.array['size'] = self.array.data.itemsize
        self.array['longargs'] = longargs
        self.array['boolargs'] = boolargs
        self.array['dblargs'] = dblargs
        self.array['longarray'] = longarray

        # create numpy arrays for the args and array
        # self.longargs = np.asarray(longargs, dtype=np.int_)
        # self.dblargs = np.asarray(dblargs, dtype=np.double)
        # self.boolargs = np.asarray(boolargs, dtype=np.int32)
        # self.longarray = np.asarray(longarray, dtype=np.int_)

    def pack(self):
        """Serialize the data."""
        data_size = self.array.data.itemsize
        if self.array.data.itemsize > ARGS_BUFFER_SIZE:
            raise RuntimeError(
                f'Message packet size {data_size} is larger than maximum {ARGS_BUFFER_SIZE}'
            )
        return self.array.data

    def unpack(self, buf):
        """Unpack buffer into our data structure."""
        self.array = np.frombuffer(buf, dtype=self.dtype)[0]


def log(message):
    global debug_log
    if debug_log is None:
        return
    f = open(debug_log, 'a')
    now = time.time()
    line = f'{now:f}\t{message}\n'
    f.write(line)
    f.close()


def logwrap(func):
    """Decorator for socket send and recv calls, so they can make log."""

    def newfunc(*args, **kwargs):
        log(f'{func}\t{args}\t{kwargs}')
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            log(f'EXCEPTION: {exc}')
            raise
        return result

    return newfunc


class GatanSocket:
    def __init__(self, host='', port=None):
        self.host = host
        if port is not None:
            self.port = port
        elif 'SERIALEMCCD_PORT' in os.environ:
            self.port = os.environ['SERIALEMCCD_PORT']
        else:
            raise ValueError(
                'Must specify a port to GatanSocket instance, or set environment variable SERIALEMCCD_PORT'
            )

        self.debug = os.environ.get('SERIALEMCCD_DEBUG', 0)
        if self.debug:
            print('host', repr(self.host))
            print('port', self.port)
            print('debug mode', os.environ['SERIALEMCCD_DEBUG'])

        self.save_frames = False
        self.num_grab_sum = 0
        self.connect()

        self.script_functions = [
            ('AFGetSlitState', 'GetEnergyFilter'),
            ('AFSetSlitState', 'SetEnergyFilter'),
            ('AFGetSlitWidth', 'GetEnergyFilterWidth'),
            ('AFSetSlitWidth', 'SetEnergyFilterWidth'),
            ('AFDoAlignZeroLoss', 'AlignEnergyFilterZeroLossPeak'),
            ('IFCGetSlitState', 'GetEnergyFilter'),
            ('IFCSetSlitState', 'SetEnergyFilter'),
            ('IFCGetSlitWidth', 'GetEnergyFilterWidth'),
            ('IFCSetSlitWidth', 'SetEnergyFilterWidth'),
            ('IFCDoAlignZeroLoss', 'AlignEnergyFilterZeroLossPeak'),
            ('IFGetSlitIn', 'GetEnergyFilter'),
            ('IFSetSlitIn', 'SetEnergyFilter'),
            ('IFGetEnergyLoss', 'GetEnergyFilterOffset'),
            ('IFSetEnergyLoss', 'SetEnergyFilterOffset'),
            ('IFGetSlitWidth', 'GetEnergyFilterWidth'),
            ('IFSetSlitWidth', 'SetEnergyFilterWidth'),
            ('GT_CenterZLP', 'AlignEnergyFilterZeroLossPeak'),
        ]
        self.filter_functions = {}
        for name, method_name in self.script_functions:
            hasScriptFunction = self.hasScriptFunction(name)
            if self.hasScriptFunction(name):
                self.filter_functions[method_name] = name
            if self.debug:
                print(name, method_name, hasScriptFunction)
        if (
            'SetEnergyFilter' in self.filter_functions.keys()
            and self.filter_functions['SetEnergyFilter'] == 'IFSetSlitIn'
        ):
            self.wait_for_filter = 'IFWaitForFilter();'
        else:
            self.wait_for_filter = ''

    def hasScriptFunction(self, name):
        script = f'if ( DoesFunctionExist("{name}") ) {{ Exit(1.0); }} else {{ Exit(-1.0); }}'
        result = self.ExecuteGetDoubleScript(script)
        return result > 0.0

    def connect(self):
        # recommended by Gatan to use localhost IP to avoid using tcp
        self.sock = socket.create_connection(('127.0.0.1', self.port))

    def disconnect(self):
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()

    def reconnect(self):
        self.disconnect()
        self.connect()

    @logwrap
    def send_data(self, data):
        return self.sock.sendall(data)

    @logwrap
    def recv_data(self, n):
        return self.sock.recv(n)

    def ExchangeMessages(self, message_send, message_recv=None):
        self.send_data(message_send.pack())

        if message_recv is None:
            return
        recv_buffer = message_recv.pack()
        recv_len = recv_buffer.itemsize

        total_recv = 0
        parts = []
        while total_recv < recv_len:
            remain = recv_len - total_recv
            new_recv = self.recv_data(remain)
            parts.append(new_recv)
            total_recv += len(new_recv)
        buf = b''.join(parts)
        message_recv.unpack(buf)
        # log the error code from received message
        sendargs = message_send.array['longargs']
        recvargs = message_recv.array['longargs']
        log(f'Func: {sendargs[0]}, Code: {recvargs[0]}')

    def GetLong(self, funcName):
        """Common class of function that gets a single long."""
        funcCode = enum_gs[funcName]
        message_send = Message(longargs=(funcCode,))
        # First recieved message longargs is error code
        message_recv = Message(longargs=(0, 0))
        self.ExchangeMessages(message_send, message_recv)
        result = message_recv.array['longargs'][1]
        return result

    def SendLongGetLong(self, funcName, longarg):
        """Common class of function with one long arg that returns a single
        long."""
        funcCode = enum_gs[funcName]
        message_send = Message(longargs=(funcCode, longarg))
        # First recieved message longargs is error code
        message_recv = Message(longargs=(0, 0))
        self.ExchangeMessages(message_send, message_recv)
        result = message_recv.array['longargs'][1]
        return result

    def GetDMVersion(self):
        return self.GetLong('GS_GetDMVersion')

    def GetNumberOfCameras(self):
        return self.GetLong('GS_GetNumberOfCameras')

    def GetPluginVersion(self):
        return self.GetLong('GS_GetPluginVersion')

    def IsCameraInserted(self, camera):
        funcCode = enum_gs['GS_IsCameraInserted']
        message_send = Message(longargs=(funcCode, camera))
        message_recv = Message(longargs=(0,), boolargs=(0,))
        self.ExchangeMessages(message_send, message_recv)
        result = bool(message_recv.array['boolargs'][0])
        return result

    def InsertCamera(self, camera, state):
        funcCode = enum_gs['GS_InsertCamera']
        message_send = Message(longargs=(funcCode, camera), boolargs=(state,))
        message_recv = Message(longargs=(0,))
        self.ExchangeMessages(message_send, message_recv)

    def SetReadMode(self, mode, scaling=1.0):
        funcCode = enum_gs['GS_SetReadMode']
        message_send = Message(longargs=(funcCode, mode), dblargs=(scaling,))
        message_recv = Message(longargs=(0,))
        self.ExchangeMessages(message_send, message_recv)

    def SetShutterNormallyClosed(self, camera, shutter):
        funcCode = enum_gs['GS_SetShutterNormallyClosed']
        message_send = Message(longargs=(funcCode, camera, shutter))
        message_recv = Message(longargs=(0,))
        self.ExchangeMessages(message_send, message_recv)

    @logwrap
    def SetK2Parameters(
        self,
        readMode,
        scaling,
        hardwareProc,
        doseFrac,
        frameTime,
        alignFrames,
        saveFrames,
        filt='',
    ):
        funcCode = enum_gs['GS_SetK2Parameters']

        self.save_frames = saveFrames

        # filter name
        filt_str = filt + '\0'
        extra = len(filt_str) % 4
        if extra:
            npad = 4 - extra
            filt_str = filt_str + npad * '\0'
        longarray = np.frombuffer(filt_str.encode(), dtype=np.int_)

        longs = [
            funcCode,
            readMode,
            hardwareProc,
        ]
        bools = [
            doseFrac,
            alignFrames,
            saveFrames,
        ]
        doubles = [
            scaling,
            frameTime,
        ]

        message_send = Message(
            longargs=longs, boolargs=bools, dblargs=doubles, longarray=longarray
        )
        message_recv = Message(longargs=(0,))  # just return code
        self.ExchangeMessages(message_send, message_recv)

    def setNumGrabSum(self, earlyReturnFrameCount, earlyReturnRamGrabs):
        # pack RamGrabs and earlyReturnFrameCount in one double
        self.num_grab_sum = (2**16) * earlyReturnRamGrabs + earlyReturnFrameCount

    def getNumGrabSum(self):
        return self.num_grab_sum

    @logwrap
    def SetupFileSaving(
        self,
        rotationFlip,
        dirname,
        rootname,
        filePerImage,
        doEarlyReturn,
        earlyReturnFrameCount=0,
        earlyReturnRamGrabs=0,
        lzwtiff=False,
    ):
        pixelSize = 1.0
        self.setNumGrabSum(earlyReturnFrameCount, earlyReturnRamGrabs)
        if self.save_frames and (doEarlyReturn or lzwtiff):
            # early return flag
            flag = 128 * int(doEarlyReturn) + 8 * int(lzwtiff)
            numGrabSum = self.getNumGrabSum()
            # set values to pass
            longs = [enum_gs['GS_SetupFileSaving2'], rotationFlip, flag]
            dbls = [pixelSize, numGrabSum, 0.0, 0.0, 0.0]
        else:
            longs = [enum_gs['GS_SetupFileSaving'], rotationFlip]
            dbls = [pixelSize]
        bools = [filePerImage]
        names_str = dirname + '\0' + rootname + '\0'
        extra = len(names_str) % 4
        if extra:
            npad = 4 - extra
            names_str = names_str + npad * '\0'
        longarray = np.frombuffer(names_str.encode(), dtype=np.int_)
        message_send = Message(
            longargs=longs, boolargs=bools, dblargs=dbls, longarray=longarray
        )
        message_recv = Message(longargs=(0, 0))
        self.ExchangeMessages(message_send, message_recv)

    # This function is broken, many undefined variables...
    # def GetFileSaveResult(self):
    #     longs = [enum_gs['GS_GetFileSaveResult'], rotationFlip]
    #     message_send = Message(longargs=longs, boolargs=bools, dblargs=dbls, longarray=longarray)
    #     message_recv = Message(longargs=(0, 0, 0))
    #     self.ExchangeMessages(message_send, message_recv)
    #     args = message_recv.array['longargs']
    #     numsaved = args[1]
    #     error = args[2]

    def SelectCamera(self, cameraid):
        funcCode = enum_gs['GS_SelectCamera']
        message_send = Message(longargs=(funcCode, cameraid))
        message_recv = Message(longargs=(0,))
        self.ExchangeMessages(message_send, message_recv)

    def UpdateK2HardwareDarkReference(self, cameraid):
        function_name = 'K2_updateHardwareDarkReference'
        return self.ExecuteSendCameraObjectionFunction(function_name, cameraid)

    def GetEnergyFilter(self):
        if 'GetEnergyFilter' not in self.filter_functions.keys():
            return -1.0
        func = self.filter_functions['GetEnergyFilter']
        script = f'if ( {func}() ) {{ Exit(1.0); }} else {{ Exit(-1.0); }}'
        return self.ExecuteGetDoubleScript(script)

    def SetEnergyFilter(self, value):
        if 'SetEnergyFilter' not in self.filter_functions.keys():
            return -1.0
        if value:
            i = 1
        else:
            i = 0
        func = self.filter_functions['SetEnergyFilter']
        wait = self.wait_for_filter
        script = f'{func}({i}); {wait}'
        return self.ExecuteSendScript(script)

    def GetEnergyFilterWidth(self):
        if 'GetEnergyFilterWidth' not in self.filter_functions.keys():
            return -1.0
        func = self.filter_functions['GetEnergyFilterWidth']
        script = f'Exit({func}())'
        return self.ExecuteGetDoubleScript(script)

    def SetEnergyFilterWidth(self, value):
        if 'SetEnergyFilterWidth' not in self.filter_functions.keys():
            return -1.0
        func = self.filter_functions['SetEnergyFilterWidth']
        script = f'if ( {func}({value:f}) ) {{ Exit(1.0); }} else {{ Exit(-1.0); }}'
        return self.ExecuteSendScript(script)

    def GetEnergyFilterOffset(self):
        if 'GetEnergyFilterOffset' not in self.filter_functions.keys():
            return 0.0
        func = self.filter_functions['GetEnergyFilterOffset']
        script = f'Exit({func}())'
        return self.ExecuteGetDoubleScript(script)

    def SetEnergyFilterOffset(self, value):
        if 'SetEnergyFilterOffset' not in self.filter_functions.keys():
            return -1.0
        func = self.filter_functions['SetEnergyFilterOffset']
        script = 'if ( {func}({value:f}) ) {{ Exit(1.0); }} else {{ Exit(-1.0); }}'
        return self.ExecuteSendScript(script)

    def AlignEnergyFilterZeroLossPeak(self):
        func = self.filter_functions['AlignEnergyFilterZeroLossPeak']
        wait = self.wait_for_filter
        script = f' if ( {func}() ) {{ {wait} Exit(1.0); }} else {{ Exit(-1.0); }}'
        return self.ExecuteGetDoubleScript(script)

    @logwrap
    def GetImage(
        self,
        processing,
        height,
        width,
        binning,
        top,
        left,
        bottom,
        right,
        exposure,  # s
        shutterDelay=0,  # ms
    ):
        """
        processing : str
            Must be one of 'dark', 'unprocessed', 'dark subtracted', 'gain normalized'
        """

        arrSize = width * height

        # TODO: need to figure out what these should be
        shutter = 0
        divideBy2 = 0
        corrections = 0
        settling = 0.0

        # prepare args for message
        if processing == 'dark':
            longargs = [enum_gs['GS_GetDarkReference']]
        else:
            longargs = [enum_gs['GS_GetAcquiredImage']]
        longargs.extend(
            [
                arrSize,  # pixels in the image
                width,
                height,
            ]
        )
        if processing == 'unprocessed':
            longargs.append(0)
        elif processing == 'dark subtracted':
            longargs.append(1)
        elif processing == 'gain normalized':
            longargs.append(2)
        longargs.extend(
            [
                binning,
                top,
                left,
                bottom,
                right,
                shutter,
            ]
        )
        if processing != 'dark':
            longargs.append(shutterDelay)
        longargs.extend(
            [
                divideBy2,
                corrections,
            ]
        )
        dblargs = [
            exposure,
            settling,
        ]

        message_send = Message(longargs=longargs, dblargs=dblargs)
        message_recv = Message(longargs=(0, 0, 0, 0, 0))

        # attempt to solve UCLA problem by reconnecting
        # if self.save_frames:
        # self.reconnect()

        self.ExchangeMessages(message_send, message_recv)

        longargs = message_recv.array['longargs']
        if longargs[0] < 0:
            return 1
        arrSize = longargs[1]
        width = longargs[2]
        height = longargs[3]
        numChunks = longargs[4]
        bytesPerPixel = 2
        numBytes = arrSize * bytesPerPixel
        chunkSize = (numBytes + numChunks - 1) / numChunks
        imArray = np.zeros((height, width), np.ushort)
        received = 0
        remain = numBytes
        for chunk in range(numChunks):
            # send chunk handshake for all but the first chunk
            if chunk:
                message_send = Message(longargs=(enum_gs['GS_ChunkHandshake'],))
                self.ExchangeMessages(message_send)
            thisChunkSize = min(remain, chunkSize)
            chunkReceived = 0
            chunkRemain = thisChunkSize
            while chunkRemain:
                new_recv = self.recv_data(chunkRemain)
                len_recv = len(new_recv)
                imArray.data[received : received + len_recv] = new_recv
                chunkReceived += len_recv
                chunkRemain -= len_recv
                remain -= len_recv
                received += len_recv
        return imArray

    def ExecuteSendCameraObjectionFunction(self, function_name, camera_id=0):
        # first longargs is error code. Error if > 0
        return self.ExecuteGetLongCameraObjectFunction(function_name, camera_id)

    def ExecuteGetLongCameraObjectFunction(self, function_name, camera_id=0):
        """Execute DM script function that requires camera object as input and
        output one long integer."""
        recv_longargs_init = (0,)
        result = self.ExecuteCameraObjectFunction(
            function_name, camera_id, recv_longargs_init=recv_longargs_init
        )
        if result is False:
            return 1
        return result.array['longargs'][0]

    def ExecuteGetDoubleCameraObjectFunction(self, function_name, camera_id=0):
        """Execute DM script function that requires camera object as input and
        output double floating point number."""
        recv_dblargs_init = (0,)
        result = self.ExecuteCameraObjectFunction(
            function_name, camera_id, recv_dblargs_init=recv_dblargs_init
        )
        if result is False:
            return -999.0
        return result.array['dblargs'][0]

    def ExecuteCameraObjectFunction(
        self,
        function_name,
        camera_id=0,
        recv_longargs_init=(0,),
        recv_dblargs_init=(0.0,),
        recv_longarray_init=[],
    ):
        """Execute DM script function that requires camera object as input."""
        if not self.hasScriptFunction(function_name):
            # unsuccessful
            return False
        fullcommand = (
            f'Object manager = CM_GetCameraManager();\n'
            f'Object cameraList = CM_GetCameras(manager);\n'
            f'Object camera = ObjectAt(cameraList,{camera_id});\n'
            f'{function_name}(camera);\n'
        )
        result = self.ExecuteScript(
            fullcommand, camera_id, recv_longargs_init, recv_dblargs_init, recv_longarray_init
        )
        return result

    def ExecuteSendScript(self, command_line, select_camera=0):
        recv_longargs_init = (0,)
        result = self.ExecuteScript(command_line, select_camera, recv_longargs_init)
        # first longargs is error code. Error if > 0
        return result.array['longargs'][0]

    def ExecuteGetLongScript(self, command_line, select_camera=0):
        """Execute DM script and return the result as integer."""
        # SerialEMCCD DM TemplatePlugIn::ExecuteScript retval is a double
        return int(self.ExecuteGetDoubleScript(command_line, select_camera))

    def ExecuteGetDoubleScript(self, command_line, select_camera=0):
        """Execute DM script that gets one double float number."""
        recv_dblargs_init = (0.0,)
        result = self.ExecuteScript(
            command_line, select_camera, recv_dblargs_init=recv_dblargs_init
        )
        return result.array['dblargs'][0]

    def ExecuteScript(
        self,
        command_line,
        select_camera=0,
        recv_longargs_init=(0,),
        recv_dblargs_init=(0.0,),
        recv_longarray_init=[],
    ):
        funcCode = enum_gs['GS_ExecuteScript']
        cmd_str = command_line + '\0'
        extra = len(cmd_str) % 4
        if extra:
            npad = 4 - extra
            cmd_str = cmd_str + (npad) * '\0'
        # send the command string as 1D longarray
        longarray = np.frombuffer(cmd_str.encode(), dtype=np.int_)
        # print(longaray)
        message_send = Message(
            longargs=(funcCode,), boolargs=(select_camera,), longarray=longarray
        )
        message_recv = Message(
            longargs=recv_longargs_init,
            dblargs=recv_dblargs_init,
            longarray=recv_longarray_init,
        )
        self.ExchangeMessages(message_send, message_recv)
        return message_recv

    def RunScript(self, fn: str, background: bool = False):
        """Run a DM script.

        fn: str
                Path to the script to run
        background: bool
                Prepend `// $BACKGROUND$` to run the script in the background
                and make it non-blocking.
        """

        bkg = r'// $BACKGROUND$\n\n'

        with open(fn) as f:
            cmd_str = ''.join(f.readlines())

        if background:
            cmd_str = bkg + cmd_str

        return self.ExecuteScript(cmd_str)


def test1():
    g = GatanSocket()
    print(g)
    ver = g.GetDMVersion()
    print('Version', ver)
    # input('enter to quit.')

    s = 'Result("Hello world\\n")'
    g.ExecuteScript(s)

    from IPython import embed

    embed()


if __name__ == '__main__':
    g = GatanSocket()

    from IPython import embed

    embed()
