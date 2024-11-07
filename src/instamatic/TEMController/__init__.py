# ruff: noqa: E402
from __future__ import annotations

import warnings

from instamatic.utils.deprecated import VisibleDeprecationWarning

warnings.warn(
    'The `TEMController` module is deprecated since version 2.0.6. Use the `controller`-module instead',
    VisibleDeprecationWarning,
    stacklevel=2,
)

from .microscope import Microscope
from .TEMController import get_instance, initialize
