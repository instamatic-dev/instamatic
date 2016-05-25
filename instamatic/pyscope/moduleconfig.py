#!/usr/bin/env python
import copy
import sys
import ConfigParser
import os
import pyscope
import pyami.fileutil


class ModuleConfigParser(object):
    def __init__(self, filename):
        self.configparser = ConfigParser.SafeConfigParser()
        self.configured = {}
        self.config_filename = filename
        self.configfiles = None

    def newHierarchyDict(self, keys, value):
        d = map((lambda x: {}), range(len(keys) + 1))
        d[0] = value
        keys.reverse()
        for i in range(len(keys)):
            d[i + 1][keys[i]] = d[i]
        return copy.deepcopy(d[len(keys)])

    def formatValue(self, name, key):
        value = None
        try:
            value = int(self.configparser.get(name, key))
        except:
            try:
                value = float(self.configparser.get(name, key))
            except:
                try:
                    value = self.configparser.getboolen(name, key)
                except:
                    valuestring = self.configparser.get(name, key)
                    if valuestring.lower() == 'true':
                        value = True
                    elif valuestring.lower() == 'false':
                        value = False
                    elif ',' in valuestring:
                        items = self.configparser.get(name, key).split(',')

                        try:
                            # list of floats for aparture sizes
                            value = map((lambda x: float(x)), items)
                            # test last value since first might be 0
                            if int(value[-1]) == value[-1]:
                                # list of integers for lens or deflector
                                # neutrals
                                value = map((lambda x: int(x)), value)
                        except:
                            # list of strings for mag mode
                            value = map((lambda x: x.strip()), items)
                    else:
                        value = valuestring
        return value

    def addHierarchyValue(self, name, levels, value):
        '''
        Add values to configured up to 3 levels.
        '''
        # This can be written perttier, but will do for now.
        if len(self.configured[name].keys()) == 0:
            self.configured[name] = self.newHierarchyDict(levels, value)
            return
        if len(levels) == 1:
            self.configured[name][levels[0]] = value
        else:
            if len(levels) == 2:
                if levels[0] not in self.configured[name].keys():
                    self.configured[name][levels[0]] = {}
                self.configured[name][levels[0]][levels[1]] = value
            if len(levels) == 3:
                if levels[0] not in self.configured[name].keys():
                    self.configured[name].update(
                        self.newHierarchyDict(levels, value))
                    return
                elif levels[1] not in self.configured[name][levels[0]].keys():
                    self.configured[name][levels[0]].update(
                        self.newHierarchyDict(levels[1:], value))
                    return
                else:
                    self.configured[name][levels[0]][
                        levels[1]][levels[2]] = value

    def convertKeys(self, keys):
        newkeys = []
        for key in keys:
            try:
                newkey = int(key)
            except:
                newkey = key
            newkeys.append(newkey)
        return newkeys

    def parse(self):
        print "parsing %s...." % self.config_filename
        # use the path of this module
        modpath = pyscope.__path__

        # read instruments.cfg
        confdirs = pyami.fileutil.get_config_dirs()
        filenames = [os.path.join(confdir, self.config_filename)
                     for confdir in confdirs]
        one_exists = False
        for filename in filenames:
            if os.path.exists(filename):
                one_exists = True
        if not one_exists:
            print 'please configure at least one of these:  %s' % (filenames,)
            sys.exit()
        try:
            self.configfiles = self.configparser.read(filenames)
        except:
            print 'error reading %s' % (filenames,)
            sys.exit()

        # parse
        names = self.configparser.sections()

        for name in names:
            self.configured[name] = {}
            hierarchy_keys = self.configparser.options(name)
            for hi_key in hierarchy_keys:
                value = self.formatValue(name, hi_key)
                levels = hi_key.split('%')
                levels = self.convertKeys(levels)
                self.addHierarchyValue(name, levels, value)
        return self.configured


def getConfigured(config_file='jeol.cfg'):
    app = ModuleConfigParser(config_file)
    configured = app.configured
    if not configured:
        configured = app.parse()
    return configured

if __name__ == '__main__':
    print getConfigured('jeol.cfg')
    raw_input('Hit any key to quit.')
