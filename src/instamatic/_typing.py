from __future__ import annotations

import os
from typing import Union

from typing_extensions import Annotated

AnyPath = Union[str, os.PathLike]
int_nm = Annotated[int, 'Length expressed in nanometers']
float_nm = Annotated[float, 'Length expressed in nanometers']
float_deg = Annotated[float, 'Angle expressed in degrees']
