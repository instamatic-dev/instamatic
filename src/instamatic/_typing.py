from __future__ import annotations

import sys

# ~~~~~~~~~~~~~~~~~~~~~~~~ TYPING EXTENSIONS ALIASES ~~~~~~~~~~~~~~~~~~~~~~~~~ #


if sys.version_info >= (3, 9):
    from typing import Annotated
else:
    from typing_extensions import Annotated


if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ CUSTOM TYPES ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


int_nm = Annotated[int, 'Length expressed in nanometers']
float_deg = Annotated[float, 'Angle expressed in degrees']
