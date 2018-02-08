from .sed_frame import *
from .cred_frame import *
from .io_frame import *
from .red_frame import *
from .ctrl_frame import *
from .debug_frame import *
from .about_frame import *
from .machine_learning_frame import *

from collections import namedtuple

Module = namedtuple('Module', ['name', 'display_name', 'tabbed', 'tk_frame'])

MODULES = (
Module("io", "i/o", False, IOFrame),
Module("cred", "cRED", True, ExperimentalcRED),
Module("sed", "serialED", True, ExperimentalSED),
Module("red", "RED", True, ExperimentalRED),
Module("ctrl", "ctrl", True, ExperimentalCtrl),
Module("learning", "learning", True, MachineLearningFrame),
Module("debug", "debug", True, DebugFrame),
Module("about", "about", True, About) )
