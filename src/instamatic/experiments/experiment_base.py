from __future__ import annotations

from abc import ABC, abstractmethod

from typing_extensions import Self


class ExperimentBase(ABC):
    """Experiment base class."""

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        pass

    @abstractmethod
    def start_collection(self, **kwargs):
        pass

    def setup(self):
        pass

    def teardown(self):
        pass

    def __enter__(self) -> Self:
        self.setup()
        return self

    def __exit__(self, kind, value, traceback):
        self.teardown()
