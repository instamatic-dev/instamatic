def is_admin():
    """Check if the current python instance has admin rights."""
    import ctypes
    import os
    try:
        is_admin = os.getuid() == 0
    except AttributeError:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

    return is_admin
