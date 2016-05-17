#!/usr/bin/env python

import sys, os

drc = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..'))  # get path of drc
sys.path.insert(0, drc)  # prepend module path to make sure it's first

from pyscope import jeolcom, simtem

# from IPython import embed

def main():
    try:
        s = jeolcom.Jeol()
    except WindowsError:
        print " >> Could not connect to JEOL, using SimTEM instead..."
        s = simtem.SimTEM()
    
    print "High tension:", s.getHighTension()
    print

    for d in s.getCapabilities():
        if 'get' in d["implemented"]:
            print "{:30s} : {}".format(d["name"], getattr(s, "get"+d["name"])())

    for x in dir(s):
        if x.startswith("get"):
            print  x

    # embed()


if __name__ == '__main__':
    main()

    