from __future__ import annotations

from abc import ABC, abstractmethod


class ExperimentBase(ABC):
    """Experiment base class."""

    @abstractmethod
    def start_collection(self):
        pass

    def setup(self):
        pass

    def teardown(self):
        pass

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, kind, value, traceback):
        self.teardown()
