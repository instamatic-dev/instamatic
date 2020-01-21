import datetime
import time


class Progress:
    """Calculate the remaining time for a running process.

    total : int
        Total number of items

    interval : int (seconds)
        Guess how long each interval is in seconds, used to estimate the first few steps.

    smoothing : float
        Exponential moving average for smoothing the time calculation, where 0.0 is no smoothing, so the last interval is used and 1.0 means the average interval is used (default: 0.3).
    """

    def __init__(self, total: int, interval: float = 1, smoothing: float = 0.3):
        super().__init__()
        self.start_time = time.perf_counter()
        self.t_last = self.start_time

        self.last_interval = self.interval = interval
        self.total = total
        self.smoothing = smoothing
        self.i = 0

    def _ema(self, current: float, last: float):
        """Estimated moving average of the current and last intervals."""
        return current * self.smoothing + last * (1 - self.smoothing)

    def update(self):
        """Update the counter and calculate a new interval.

        This must be called every iteration.
        """
        self.i += 1
        t = time.perf_counter()
        interval = t - self.t_last
        self.last_interval = self.interval = self._ema(interval, self.last_interval)
        self.t_last = t

    def remaining(self) -> int:
        """Return the current remaining time estimate (seconds)"""
        eta = ((self.total - self.i) * self.interval)  # s
        return int(eta)

    def remaining_dt(self) -> int:
        """Return the current remaining time estimate (as datetime object)"""
        t = self.remaining()  # round to nearest second
        return datetime.timedelta(seconds=t)

    def jump_to(self, i: int) -> None:
        """Jump to a new index `i`"""
        self.i = i
