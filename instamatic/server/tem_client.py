from instamatic import config
from instamatic.TEMController.microscope_client import MicroscopeClient

microscope_id = config.microscope.name


if __name__ == '__main__':
    # Usage:
    # First run tem_server.py (or `instamatic.temserver.exe`)
    # Second, run tem_client.py

    tem = MicroscopeClient(microscope_id)

    from IPython import embed
    embed()
