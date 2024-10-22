from abc import ABC, abstractmethod

class ExperimentBase(ABC):
    """Experiment base class"""

    @abstractmethod
    def start_collection():
        pass
    