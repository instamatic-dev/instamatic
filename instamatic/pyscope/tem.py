# The Leginon software is Copyright 2004
# The Scripps Research Institute, La Jolla, CA
# For terms of the license agreement
# see http://ami.scripps.edu/software/leginon-license
#

import baseinstrument
import config


class TEM(baseinstrument.BaseInstrument):
    name = None
    capabilities = baseinstrument.BaseInstrument.capabilities + (
        # get only
        {'name': 'ColumnPressure', 'type': 'property'},
        {'name': 'ColumnValvePositions', 'type': 'property'},
        {'name': 'ExternalShutterStates', 'type': 'property'},
        {'name': 'FilmAutomaticExposureTime', 'type': 'property'},
        {'name': 'FilmDateTypes', 'type': 'property'},
        {'name': 'FilmExposureTime', 'type': 'property'},
        {'name': 'FilmExposureTypes', 'type': 'property'},
        {'name': 'HighTensionState', 'type': 'property'},
        {'name': 'HighTensionStates', 'type': 'property'},
        {'name': 'HolderStatus', 'type': 'property'},
        {'name': 'HolderTypes', 'type': 'property'},
        {'name': 'LowDoseModes', 'type': 'property'},
        {'name': 'LowDoseStates', 'type': 'property'},
        {'name': 'Magnifications', 'type': 'property'},
        {'name': 'MainScreenMagnification', 'type': 'property'},
        {'name': 'MainScreenPositions', 'type': 'property'},
        {'name': 'ObjectiveExcitation', 'type': 'property'},
        {'name': 'ScreenCurrent', 'type': 'property'},
        {'name': 'ShutterPositions', 'type': 'property'},
        {'name': 'SmallScreenPosition', 'type': 'property'},
        {'name': 'SmallScreenPositions', 'type': 'property'},
        {'name': 'StageStatus', 'type': 'property'},
        {'name': 'VacuumStatus', 'type': 'property'},

        # get/set
        {'name': 'BeamBlank', 'type': 'property'},
        {'name': 'BeamShift', 'type': 'property'},
        {'name': 'BeamTilt', 'type': 'property'},
        {'name': 'ColumnValvePosition', 'type': 'property'},
        {'name': 'CorrectedStagePosition', 'type': 'property'},
        {'name': 'DarkFieldMode', 'type': 'property'},
        {'name': 'Defocus', 'type': 'property'},
        {'name': 'DiffractionMode', 'type': 'property'},
        {'name': 'Emission', 'type': 'property'},
        {'name': 'ExternalShutter', 'type': 'property'},
        {'name': 'FilmDateType', 'type': 'property'},
        {'name': 'FilmExposureNumber', 'type': 'property'},
        {'name': 'FilmExposureType', 'type': 'property'},
        {'name': 'FilmManualExposureTime', 'type': 'property'},
        {'name': 'FilmStock', 'type': 'property'},
        {'name': 'FilmText', 'type': 'property'},
        {'name': 'FilmUserCode', 'type': 'property'},
        {'name': 'Focus', 'type': 'property'},
        {'name': 'GunShift', 'type': 'property'},
        {'name': 'GunTilt', 'type': 'property'},
        {'name': 'HighTension', 'type': 'property'},
        {'name': 'HolderType', 'type': 'property'},
        {'name': 'ImageShift', 'type': 'property'},
        {'name': 'Intensity', 'type': 'property'},
        {'name': 'LowDose', 'type': 'property'},
        {'name': 'LowDoseMode', 'type': 'property'},
        {'name': 'Magnification', 'type': 'property'},
        {'name': 'MainScreenPosition', 'type': 'property'},
        {'name': 'ProbeMode', 'type': 'property'},
        {'name': 'RawImageShift', 'type': 'property'},
        {'name': 'Shutter', 'type': 'property'},
        {'name': 'SpotSize', 'type': 'property'},
        {'name': 'StagePosition', 'type': 'property'},
        {'name': 'Stigmator', 'type': 'property'},
        {'name': 'TurboPump', 'type': 'property'},
        {'name': 'ProjectionSubModeMap', 'type': 'property'},

        # methods
        {'name': 'filmExposure', 'type': 'method'},
        {'name': 'findMagnifications', 'type': 'method'},
        {'name': 'normalizeLens', 'type': 'method'},
        {'name': 'postFilmExposure', 'type': 'method'},
        {'name': 'preFilmExposure', 'type': 'method'},
        {'name': 'resetDefocus', 'type': 'method'},
        {'name': 'relaxBeam', 'type': 'method'},
        {'name': 'runBufferCycle', 'type': 'method'},

        # optional:
        {'name': 'EnergyFilter', 'type': 'property'},
        {'name': 'EnergyFilterWidth', 'type': 'property'},
    )

    def __init__(self):
        baseinstrument.BaseInstrument.__init__(self)
        self.config_name = config.getNameByClass(self.__class__)
        try:
            self.cs = config.getConfigured()[self.config_name]['cs']
        except KeyError:
            self.cs = None
            print " >> Cannot find 'cs' in config..."
        self.projection_submode_map = {}

    def getCs(self):
        return self.cs

    def getEnergyFiltered(self):
        return False

    def exposeSpecimenNotCamera(self, seconds):
        raise NotImplementedError()

    def getProbeMode(self):
        return 'default'

    def setProbeMode(self, probe_str):
        pass

    def getProbeModes(self):
        return ['default']

    def getProjectionSubModeMap(self):
        return self.projection_submode_map

    def setProjectionSubModeMap(self, mode_map):
        '''
        called by EM.py to set self.projetion_submode_map
        {mag:(mode_name,mode_id)}
        '''
        self.projection_submode_map = mode_map

    def addProjectionSubModeMap(self, mag, mode_name, mode_id, overwrite=False):
        # Only do it once
        overwritten = False
        if mag in self.projection_submode_map.keys():
            if not overwrite:
                return overwritten
            else:
                overwritten = True
        self.projection_submode_map[mag] = (mode_name, mode_id)
        return overwritten

    def getProjectionSubModeName(self):
        mag = self.getMagnification()
        try:
            return self.projection_submode_map[mag][0]
        except:
            # get an error if setProjectionSubModeMapping is not called from
            # leginon/EM.py
            raise NotImplementedError()

    def relaxBeam(self, steps=3, interval=0.1, totaltime=2):
        '''
        Only needed for JEOL scopes
        '''
        pass
