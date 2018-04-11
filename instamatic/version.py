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
__long_title__ = "{} v{}".format(__title__, __version__)
__author__ = "Stef Smeets"
__author_email__ = "stef.smeets@mmk.su.se"
__description__ = "Python program to collect serial and rotation electron diffraction data"
__license__ = "GPLv3"
__url__ = "http://github.com/stefsmeets/instamatic"
__citation__ = "S. Smeets, B. Wang, M.O. Cichocka, J. Ångström, & W. Wan. (2018, April 11). Instamatic (Version 0.6). Zenodo. http://doi.org/10.5281/zenodo.1217026"

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
