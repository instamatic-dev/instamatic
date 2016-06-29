#!/usr/bin/env python

import sys
import ConfigParser
import imp
import os
import inspect
import instamatic.pyscope
import instamatic.pyscope.tem
import instamatic.pyscope.ccdcamera
from instamatic.pyami import fileutil

configured = {}
temclasses = None
cameraclasses = None
configfiles = None


def parse():
    global configured, temclasses, cameraclasses, configfiles

    configparser = ConfigParser.SafeConfigParser()

    # use the path of this module
    modpath = instamatic.pyscope.__path__

    # read instruments.cfg
    confdirs = fileutil.get_config_dirs()
    filenames = [os.path.join(confdir, 'instruments.cfg')
                 for confdir in confdirs]
    one_exists = False
    for filename in filenames:
        if os.path.exists(filename):
            one_exists = True
    if not one_exists:
        print 'please configure at least one of these:  %s' % (filenames,)
        sys.exit()
    try:
        configfiles = configparser.read(filenames)
    except:
        print 'error reading %s' % (filenames,)
        sys.exit()

    # parse
    names = configparser.sections()
    temclasses = []
    cameraclasses = []
    mods = {}

    for name in names:
        configured[name] = {}
        cls_str = configparser.get(name, 'class')
        modname, clsname = cls_str.split('.')
        if modname not in mods:
            fullmodname = 'instamatic.pyscope.' + modname
            args = imp.find_module(modname, modpath)
            try:
                mod = imp.load_module(fullmodname, *args)
            finally:
                if args[0] is not None:
                    args[0].close()
            mods[modname] = mod
        mod = mods[modname]
        cls = getattr(mod, clsname)
        if issubclass(cls, instamatic.pyscope.tem.TEM):
            try:
                cs_str = configparser.get(name, 'cs')
                cs_value = float(cs_str)
            except:
                cs_value = None
            configured[name]['cs'] = cs_value
            temclasses.append(cls)
        if issubclass(cls, instamatic.pyscope.ccdcamera.CCDCamera):
            cameraclasses.append(cls)
            try:
                z_str = configparser.get(name, 'zplane')
                z_value = int(z_str)
            except:
                z_value = 0
            configured[name]['zplane'] = z_value
            for key in ('height', 'width'):
                try:
                    configured[name][key] = int(configparser.get(name, key))
                except:
                    pass
        try:
            log = configparser.get(name, 'log')
        except:
            log = None
        configured[name]['log'] = log
        configured[name]['class'] = cls

    return configured, temclasses, cameraclasses


def getConfigured():
    global configured
    if not configured:
        parse()
    return configured


def getTEMClasses():
    global temclasses
    if temclasses is None:
        parse()
    return temclasses


def getCameraClasses():
    global cameraclasses
    if cameraclasses is None:
        parse()
    return cameraclasses


def getNameByClass(cls):
    conf = getConfigured()
    for bcls in inspect.getmro(cls):
        for name, value in conf.items():
            if bcls.__name__ == value['class'].__name__:
                return name
