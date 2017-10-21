from SEDframe import *
from cREDframe import *
from IOFrame import *
from REDframe import *
from CtrlFrame import *
from debugframe import *

from collections import namedtuple

Module = namedtuple('Module', ['name', 'display_name', 'tabbed', 'tk_frame'])

MODULES = (
Module("io", "i/o", False, IOFrame),
Module("cred", "cRED", True, ExperimentalcRED),
Module("sed", "serialED", True, ExperimentalSED),
Module("red", "RED", True, ExperimentalRED),
Module("ctrl", "ctrl", True, ExperimentalCtrl),
Module("debug", "debug", True, DebugFrame) )