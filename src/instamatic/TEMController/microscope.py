from __future__ import annotations

from instamatic.utils.deprecated import deprecated


@deprecated(since='2.0.6', alternative='instamatic.microscope.get_microscope_class')
def get_tem(interface: str) -> 'type[MicroscopeBase]':
    from instamatic.microscope import get_microscope_class

    return get_microscope_class(interface=interface)
