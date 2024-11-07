from __future__ import annotations

from instamatic.microscope.base import MicroscopeBase
from instamatic.utils.deprecated import deprecated

__all__ = ['Microscope', 'get_tem']


@deprecated(since='2.0.6', alternative='instamatic.microscope.get_microscope_class')
def get_tem(interface: str) -> 'type[MicroscopeBase]':
    from instamatic.microscope import get_microscope_class

    return get_microscope_class(interface=interface)


@deprecated(since='2.0.6', alternative='instamatic.microscope.get_microscope')
def Microscope(name: str = None, use_server: bool = False) -> MicroscopeBase:
    from instamatic.microscope import get_microscope

    return get_microscope(name=name, use_server=use_server)
