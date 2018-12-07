# # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#    _           _                        _   _         #
#   (_)_ __  ___| |_ __ _ _ __ ___   __ _| |_(_) ___    #
#   | | '_ \/ __| __/ _` | '_ ` _ \ / _` | __| |/ __|   #
#   | | | | \__ \ || (_| | | | | | | (_| | |_| | (__    #
#   |_|_| |_|___/\__\__,_|_| |_| |_|\__,_|\__|_|\___|   #
#                                                       #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # #

VERSION = (0, 6, 0)

__version__ = "{}.{}.{}".format(*VERSION)
__title__ = "instamatic"
__long_title__ = f"{__title__} v{__version__}"
__author__ = "Stef Smeets"
__author_email__ = "stef.smeets@mmk.su.se"
__description__ = "Python program to collect serial and rotation electron diffraction data"
__license__ = "GPLv3"
__url__ = "http://github.com/stefsmeets/instamatic"
__doi__ = "https://doi.org/10.5281/zenodo.1217026"
__citation__ = f"Zenodo (2018). Instamatic (Version 0.6), {__doi__}"
__citation_cred__ = "J. Appl. Cryst. (2018). 51, 1652–1661, https://doi.org/10.1107/S1600576718015145"
__citation_serialed__ = "J. Appl. Cryst. (2018). 51, 1262–1273, https://doi.org/10.1107/S1600576718009500"


def register_thank_you_message():
    import atexit
    import textwrap

    def message():
        msg = f"Thank you for using {__long_title__}. If you found this software useful, please consider citing it: {__citation__}"
        
        h = "+"*74
        lines = [f"+ {line:70} +" for line in textwrap.wrap(msg)]

        msg = textwrap.fill(msg)

        for line in ["", h, *lines, h, ""]:
            print(line)

    atexit.register(message)
