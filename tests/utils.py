from __future__ import annotations

from typing_extensions import Self


class InstanceAutoTracker:
    """Track cls instances: useful for @pytest.mark.parametrize dataclasses"""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls.INSTANCES: list[Self] = []

    def __post_init__(self) -> None:
        self.__class__.INSTANCES.append(self)
