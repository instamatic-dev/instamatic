import threading
import time

class Watcher(threading.Thread):
    """
    Continuously monitor output of an (i/o bound) function

    f: callable
        Function to watch
    interval: float
        Interval in seconds between function calls

    Usage:
        w = Watcher(ctrl.StagePosition.Get)
        current = w.get()
    """
    def __init__(self, func, interval=1.0):
        super(Watcher, self).__init__()
        self.func = func
        self.interval = interval
        self.setDaemon(True)
        self.current = None

    def run(self):
        while True:
            time.sleep(self.interval)
            self.current = self.func()

    def get(self):
        return self.current
