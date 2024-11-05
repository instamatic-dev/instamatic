import warnings
from instamatic.utils.deprecated import VisibleDeprecationWarning

warnings.warn("The `TEMController` module is deprecated since version 2.0.6. Use the `controller`-module instead", VisibleDeprecationWarning)

from instamatic.microscope import Microscope
from instamatic.controller import get_instance, initialize
