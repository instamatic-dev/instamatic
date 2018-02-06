from __future__ import print_function
from ctypes import *
from ctypes.wintypes import UINT
from ctypes.wintypes import DWORD
import threading

"""High resolution timer based on Win32 multimedia timer
https://msdn.microsoft.com/en-us/library/windows/desktop/dd757664(v=vs.85).aspx
https://stackoverflow.com/a/16315086
"""

timeproc = WINFUNCTYPE(None, c_uint, c_uint, DWORD, DWORD, DWORD)
timeSetEvent = windll.winmm.timeSetEvent
timeKillEvent = windll.winmm.timeKillEvent

RESOLUTION = UINT(0)
USER_DATA = c_ulong(0)
PERIODIC = c_uint(False)


def wait(delay):
    """Delay execution for a given number of milliseconds. The argument must be
    an integer number and has millisecond precision."""
    DELAY = UINT(delay)
    pause_event = threading.Event()
    
    def callback_func(uID, uMsg, dwUser, dw1, dw2):
        pause_event.set()

    CALLBACK = timeproc(callback_func)

    eventid = timeSetEvent(DELAY, RESOLUTION, CALLBACK, USER_DATA, PERIODIC)
    pause_event.wait()
    timeKillEvent(eventid)


if __name__ == '__main__':
    import time

    t0 = time.clock()
    wait(20)
    t1 = time.clock()
    
    print("time", t1-t0)

    t0 = time.clock()
    wait(2)
    t1 = time.clock()
    print("time", t1-t0)
    