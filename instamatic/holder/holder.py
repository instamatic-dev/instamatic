from instamatic import config

default_holder_interface = config.microscope.interface

__all__ = ['Holder', 'get_holder']


def get_holder(interface: str):
    """Grab holder class with the specific 'interface'."""

    if interface == 'xnano':
        from .XNano import XNanoHolder as cls
    else:
        raise ValueError(f'No such holder interface: `{interface}`')

    return cls


def Holder(name: str = None):
    """Generic class to load holder interface class.

    name: str
        Specify which holder to use

    returns: Holder interface class
    """

    if name is None:
        interface = default_holder_interface
        name = interface
    elif name != config.settings.holder:
        config.load_holder_config(holder_name=name)
        interface = config.holder.interface
    else:
        interface = config.holder.interface

    cls = get_holder(interface)
    holder = cls(name=name)

    return holder
