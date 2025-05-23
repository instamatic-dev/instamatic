from __future__ import annotations

import json
import os
import time
from contextlib import ContextDecorator
from functools import wraps
from statistics import mean, stdev
from typing import Any, Dict, List, Optional

from typing_extensions import Self


class PerformanceTracker(ContextDecorator):
    """A context manager and decorator that tracks the ratio between process
    time and wall time for wrapped functions/code blocks and saves statistics
    to a JSON file."""

    _metrics: Dict[str, List[float]] = {}
    _output_file: str = 'performance_metrics.json'

    def __init__(self, name: Optional[str] = None):
        self.name = name
        self.start_wall_time = 0.0

    def __enter__(self) -> Self:
        self.start_wall_time = time.process_time_ns()
        return self

    def __exit__(self, *exc) -> None:
        wall_time = (time.process_time_ns() - self.start_wall_time) * 1e-3

        # Calculate ratio (process_time / wall_time)
        # Ratio close to 1 means CPU-bound, close to 0 means IO-bound
        times = wall_time if wall_time > 0 else 0

        if self.name not in self._metrics:
            self._metrics[self.name] = []
        self._metrics[self.name].append(times)
        if len(self._metrics[self.name]) == 600:
            self._save_metrics()
        return False

    def __call__(self, func):
        if self.name is None:
            self.name = func.__name__

        @wraps(func)
        def wrapped(*args, **kwargs):
            with self:
                return func(*args, **kwargs)

        return wrapped

    @classmethod
    def set_output_file(cls, filename: str) -> None:
        """Set the output JSON file path."""
        cls._output_file = filename

    @classmethod
    def _save_metrics(cls) -> None:
        """Save performance metrics to JSON file with statistics."""
        try:
            # Load existing metrics if file exists
            existing_data = {}
            if os.path.exists(cls._output_file):
                with open(cls._output_file, 'r') as f:
                    existing_data = json.load(f)

            # Calculate statistics for current run
            stats = {}
            for name, times in cls._metrics.items():
                times = times[100:]  # cut first frames where it stabilizes
                if len(times) > 1:
                    stats[name] = {
                        'mean': mean(times),
                        'std': stdev(times),
                        'samples': len(times),
                    }
                else:
                    stats[name] = {
                        'mean': times[0] if times else 0,
                        'std': 0,
                        'samples': len(times),
                    }

            # Update existing data with new stats
            existing_data.update(stats)

            # Write updated data back to file
            with open(cls._output_file, 'w') as f:
                json.dump(existing_data, f, indent=4)

        except Exception as e:
            print(f'Error saving metrics: {e}')
        finally:
            assert False  # just kill the program
