from __future__ import annotations

import sys

if sys.version_info >= (3, 9):
    from typing import Annotated

    int_nm = Annotated[int, 'Length expressed in nanometers']
    float_deg = Annotated[float, 'Angle expressed in degrees']
else:
    int_nm = int
    float_deg = float
