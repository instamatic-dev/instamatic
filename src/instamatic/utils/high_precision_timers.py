import atexit
import ctypes
from ctypes import wintypes

winmm = ctypes.WinDLL('winmm')

ENABLED = False


class TIMECAPS(ctypes.Structure):
    _fields_ = (('wPeriodMin', wintypes.UINT),
                ('wPeriodMax', wintypes.UINT))


def enable(milliseconds: int = 1) -> None:
    """Set up the system for increased timer precision, e.g. time.sleep(). Will
    be reset to the default of 10 ms once the parent process is killed. This
    effect is system-wide.

    https://docs.microsoft.com/en-us/windows/desktop/api/timeapi/
    """
    global ENABLED
    if ENABLED:
        # print("High precision timers are already enabled")
        return

    caps = TIMECAPS()
    winmm.timeGetDevCaps(ctypes.byref(caps), ctypes.sizeof(caps))
    milliseconds = min(max(milliseconds, caps.wPeriodMin), caps.wPeriodMax)

    winmm.timeBeginPeriod(milliseconds)

    # print(f"Change time period to {milliseconds} ms")

    def reset_time_period():
        # print(f"Reset time period from milliseconds{} ms")
        winmm.timeEndPeriod(milliseconds)

    atexit.register(reset_time_period)
    ENABLED = True


if __name__ == '__main__':
    import timeit

    setup = 'import time'
    stmt = 'time.sleep(0.001)'
    print(timeit.timeit(stmt, setup, number=1000))

    print('change time period')
    enable(1)

    setup = 'import time'
    stmt = 'time.sleep(0.001)'
    print(timeit.timeit(stmt, setup, number=1000))
