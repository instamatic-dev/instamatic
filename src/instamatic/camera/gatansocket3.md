## gatansocket3.py

`gatansocket3.py` defines a client class to interface with the socket based DM plugin.

The script adapted from [Leginon](http://emg.nysbc.org/redmine/projects/leginon/wiki/Leginon_Homepage). Leginon is licenced under the Apache License, Version 2.0. The code (`gatansocket3.py`) was converted from Python2.7 to Python3.6+ from [here](http://emg.nysbc.org/redmine/projects/leginon/repository/revisions/trunk/entry/pyscope/gatansocket.py).

It needs the SERIALEMCCD plugin to be installed in DigitalMicrograph. The relevant instructions from the [SerialEM documentation](https://bio3d.colorado.edu/SerialEM/hlp/html/setting_up_serialem.htm) are referenced below.

### Setup [1]

To connect to DigitalMicrograph through a socket interface on the same or a different computer, such as for a K2/K3 camera with SerialEM running on an FEI microscope, you need to do the following:
 - Determine the IP address of the computer running DM on the network which that computer shares with the computer running SerialEM.  If SerialEM and DM are running on the same computer, use `127.0.0.1` for the address.
 - Copy the appropriate SerialEMCDD plugin from the SerialEM_3-x-x folder to a Plugins folder on the other computer (the one running DM). Specifically:
     - If the other computer is running 64-bit Windows, copy  `SEMCCD-GMS2.31-64.dll`, `SEMCCD-GMS3.30-64.dll`, or `SEMCCD-GMS3.31-64.dll` to `C:\ProgramData\Gatan\Plugins` and rename it to `SEMCCD-GMS2-64.dll`
     - If the other computer is running GMS2 on Windows XP or Windows 7 32-bit, copy `SEMCCD-GMS2.0-32.dll` or `SEMCCD-GMS2.3-32.dll` to `C:\Program Files\Gatan\Plugins` and rename it to `SEMCCD-GMS2-32.dll`
     - If the other computer is running GMS 1, copy `SerialEMCCD.dll` to `C:\Program Files\Gatan\DigitalMicrograph\Plugins`
 - If DM and SerialEM are running on the same computer, the installer should have placed the right plugin in the right folder, but if not, follow the procedure just given.
 - On the computer running DM, define a system environment variable `SERIALEMCCD_PORT` with the value `48890` or other selected port number, as described in the section above.
 - Make sure that this port is open for communication between SerialEM and DM. If there is any possibility of either machine being exposed to the internet, do not simply turn off the firewalls; open only this specific port in the firewall, and allow access only by the other machine or the local subnet.  Even if just this one port is exposed to the world, port scanners can interfere with communication and DM function.
 - Restart DM. Note that no registration is needed for the plugin when using a socket interface.
 - If the connection does not work, debugging output can be obtained on both sides by:
     - Setting an environment variable `SERIALEMCCD_DEBUG` with the value of `1` or `2`, where `2` will give more verbose output related to the socket operations.

[1]. https://bio3d.colorado.edu/SerialEM/hlp/html/setting_up_serialem.htm
