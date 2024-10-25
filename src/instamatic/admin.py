from __future__ import annotations

import ctypes
import sys

# Adapted from https://stackoverflow.com/a/41930586


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except BaseException:
        return False


def run_as_admin(fn):
    ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, fn, None, 1)
