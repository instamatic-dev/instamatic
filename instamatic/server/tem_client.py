# coding: future_fstrings 

from instamatic import config
from instamatic.TEMController.server_microscope import ServerMicroscope

microscope_id = config.microscope.name


if __name__ == '__main__':
    ## Usage: 
    ##    First run tem_server.py (or `instamatic.temserver.exe`)
    ##    Second, run tem_client.py

    tem = ServerMicroscope(microscope_id)

    from IPython import embed
    embed()
