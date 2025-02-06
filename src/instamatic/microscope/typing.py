from __future__ import annotations

from typing import NamedTuple

from instamatic.typing import float_deg, int_nm


class StagePositionTuple(NamedTuple):
    x: int_nm
    y: int_nm
    z: int_nm
    a: float_deg
    b: float_deg
