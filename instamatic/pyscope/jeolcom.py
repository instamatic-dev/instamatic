import time
import math
import sys
import comtypes.client
import tem
import moduleconfig

import atexit

@atexit.register
def exit_func():
    """Uninitialize comtypes to prevent the program from hanging"""
    comtypes.CoUninitialize()
    print "Uninitialize com connection to microscope"

DEBUG = True

# function modes
FUNCTION_MODES = {'mag1':0,'mag2':1,'lowmag':2,'samag':3,'diff':4}
FUNCTION_MODE_ORDERED_NAMES = ['mag1','mag2','lowmag','samag','diff']

# identifier for dector
MAIN_SCREEN = 13

# MDS modes
MDS_OFF = 0
MDS_SEARCH = 1
MDS_FOCUS = 2
MDS_PHOTO = 3

# aperture ids
CLA = 1
OLA = 2
HCA = 3
SAA = 4

# constants for Jeol Hex value
ZERO = 32768
MAX = 65535
MIN = 0
SCALE_FACTOR = 32767

# coarse-fine ratio for OL
COARSE_SCALE = 32

def debug_print(message):
    if DEBUG:
        print message

def toJeol(val):
    return ZERO + int(round(SCALE_FACTOR * val))

def toLeginon(val):
    return float(val - ZERO)/SCALE_FACTOR

class Jeol(tem.TEM):
    name = 'Jeol'
    def __init__(self):
        tem.TEM.__init__(self)

        # initial COM in multithread mode if not initialized otherwise
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except WindowsError:
            comtypes.CoInitialize()

        # get the JEOL COM library and create the TEM3 object
        temext = comtypes.client.GetModule(('{CE70FCE4-26D9-4BAB-9626-EC88DB7F6A0A}', 3, 0))
        self.tem3 = comtypes.client.CreateObject(temext.TEM3, comtypes.CLSCTX_ALL)

        # initialize each interface from the TEM3 object
        self.ht3 = self.tem3.CreateHT3()
        self.eos3 = self.tem3.CreateEOS3()
        self.lens3 = self.tem3.CreateLens3()
        self.def3 = self.tem3.CreateDef3()
        self.detector3 = self.tem3.CreateDetector3()
        self.camera3 = self.tem3.CreateCamera3()
        self.mds3 = self.tem3.CreateMDS3()
        self.stage3 = self.tem3.CreateStage3()
        self.feg3 = self.tem3.CreateFEG3()
        self.filter3 = self.tem3.CreateFilter3()
        self.apt3 = self.tem3.CreateApt3()
        self.backlash_start = 10e-6
        self.backlash_pause = 0.1

        # wait for interface to activate
        result = None
        timeout = False
        t0 = time.time()
        while result != 0 and not timeout:
            ht, result = self.ht3.GetHTValue()
            time.sleep(1)
            t1 = time.time()
            if t1-t0 > 60:
                timout = True
                sys.exit(1)

        self.setJeolConfigs()
        self.has_auto_apt = self.testAutomatedAperture()
        self.relax_beam = False

        self.magnifications = []
        # submode_mags keys are submode_indices and values are magnification list in the submode
        self.submode_mags = {}
        # initialize values from jeol.cfg
        self.zero_defocus_om = self.getJeolConfig('om standard focus')
        self.zero_defocus_ol = self.getJeolConfig('ol standard focus')
        self.stage_limit = self.getJeolConfig('stage','stage_limit')
        self.backlash_scale = self.getJeolConfig('stage','backlash_scale')
        self.backlash_limit = self.getJeolConfig('stage','backlash_limit')
    
    def __del__(self):
        comtypes.CoUninitialize()

    def setJeolConfigs(self):
        self.jeolconfigs = moduleconfig.getConfigured('jeol.cfg')

    def getJeolConfig(self,optionname,itemname=None):
        if itemname is None:
            return self.jeolconfigs[optionname]
        else:
            return self.jeolconfigs[optionname][itemname]

    def testAutomatedAperture(self):
        if not self.getJeolConfig('tem option','use_auto_apt'):
            return False
        result = 10000
        for i in range(10):
            if result != 0:
                time.sleep(.1)
                result = self.apt3.SelectKind(2)
        # result is 0 if there is no error
        return result == 0

    def subDivideMode(self,mode_name,mag):
        if mode_name == 'mag1':
            # TO DO: need to check key exists
            if mag > self.getJeolConfig('tem option','ls4_mag_max'):
                return 'ls5'
            elif mag > self.getJeolConfig('tem option','ls3_mag_max'):
                return 'ls4'
            elif mag > self.getJeolConfig('tem option','ls2_mag_max'):
                return 'ls3'
            elif mag > self.getJeolConfig('tem option','ls1_mag_max'):
                return 'ls2'
            else:
                return 'ls1'
        if mode_name == 'lowmag':
            if mag <= self.getJeolConfig('tem option','lm1_mag_max'):
                return 'lm1'
        return mode_name

    def getScale(self,key,mag=None):
        '''
        Get Scale Factor set in jeol.cfg. If axes are involved, return
        values for all axes
        '''
        options = {'beamtilt':'def','beamshift':'def','imageshift':'def','focus':'lens','stage':'stage'}
        optionname = options[key]
        value = self.getJeolConfig(optionname,key+'_scale')
        if key == 'stage' or key == 'beamtilt':
            return value
        else:
            if mag is None:
                mag = self.getMagnification()
            try:
                mode_name,mode_id = self.projection_submode_map[mag]
                # depends on mag to choose ['ls1','ls2','ls3','lm1']
                mode_subname = self.subDivideMode(mode_name,mag)
                return value[mode_subname]
            except:
                raise RuntimeError('%s function not implemented in mag %d' % (key,mag))

    def getNeutral(self,key,mag=None):
        '''
        Get Scale Factor set in jeol.cfg. If axes are involved, return
        values for all axes
        Valid keys are 'beamshift','imageshift','beamtilt'
        '''
        optionname = 'neutral '+key
        value = [0,0]

        if mag is None:
            mag = self.getMagnification()
        try:
            value = self.getJeolConfig(optionname,mag)
        except:
            try:
                lens_series = self.getLensSeriesDivision(mag)
                value = self.getJeolConfig(optionname,lens_series)
            except:
                debug_print('%s,%d') % (optionname,int(mag))
                raise RuntimeError('%s function not configured at mag %d' % (key,mag))
        return {'x':value[0],'y':value[1]}

    def getLimit(self,key):
        if key == 'piezo':
            #2100F at NYSBC
            return {'x':1.75e-6,'y':1.17e-6}

    def setProjectionSubModes(self):
        mode_names = self.getJeolConfig('eos','use_modes')
        for name in mode_names:
            mode_index = FUNCTION_MODES[name]
            self.projection_submodes[mode_index] = name

    def setProjectionSubModeMap(self, mode_map):
        '''
        called by EM.py to set self.projetion_submode_map
        self.projection_submode_map {mag:(mode_name,mode_id)}
        and
        self.submode_mags {mode_id:[mags]}
        '''
        self.projection_submode_map = mode_map
        self.setProjectionSubModeMags()

    def getBacklashParams(self):
        return self.backlash_limit,self.backlash_pause

    def setBacklashParams(self, skip, pause):
        self.backlash_limit = skip
        self.backlash_pause = pause

    def setProjectionSubModeMags(self):
        '''
        initialize a dictionary of submode_indices
        mapped to sorted magnification list
        '''
        # self.projection_submode_map key is mag, and item is (mode_name, mode_index)
        # self.submode_mags key is mode_index, and item is sorted mag list
        if not self.submode_mags:
            for m in self.projection_submode_map:
                v = self.projection_submode_map[m]
                if v[1] not in self.submode_mags.keys():
                    self.submode_mags[v[1]] = []
                self.submode_mags[v[1]].append(m)
            map((lambda x: self.submode_mags[x].sort()),self.submode_mags.keys())

    def normalizeLens(self, lens = "all"):
        pass

    def getGunTilt(self):
        tilt_x, tilt_y, result = self.def3.GetGunA1()
        return {'x' : toLeginon(tilt_x), 'y' : toLeginon(tilt_y)}
 
    def setGunTilt(self, vector, relative = "absolute"):
        current_tilt = self.getGunTilt()
        tilt_x = current_tilt['x']
        tilt_y = current_tilt['y']
        if relative == 'relative':
            if 'x' in vector:
                tilt_x += vector['x']
            if 'y' in vector:
                tilt_y += vector['y']
        elif relative == 'absolute':
            if 'x' in vector:
                tilt_x = vector['x']
            if 'y' in vector:
                tilt_y = vector['y']
        else:
            raise ValueError

        self.def3.SetGunA1(toJeol(tilt_x), toJeol(tilt_y))

    def getGunShift(self):
        shift_x, shift_y, result = self.def3.GetGunA2()
        return {'x' : toLeginon(shift_x), 'y' : toLeginon(shift_y)}

    def setGunShift(self, vector, relative = "absolute"):
        current_shift = self.getGunShift()
        shift_x = current_shift['x']
        shift_y = current_shift['y']
        if relative == 'relative':
            if 'x' in vector:
                shift_x += vector['x']
            if 'y' in vector:
                shift_y += vector['y']
        elif relative == 'absolute':
            if 'x' in vector:
                shift_x = vector['x']
            if 'y' in vector:
                shift_y = vector['y']
        else:
            raise ValueError

        self.def3.SetGunA2(toJeol(shift_x), toJeol(shift_y))
 
    def getHighTensionStates(self):
        return ['off', 'on', 'disabled']

    def getHighTension(self):
        ht, result = self.ht3.GetHTValue()
        return float(ht)

    def setHighTension(self, ht):
#       result = self.ht3.SetHTValue(float(ht))
        pass

    def getColumnValvePositions(self):
        return ['open', 'closed']

    def getColumnValvePosition(self):
        position, result = self.feg3.GetBeamValve()
        if position:
            return 'open'
        else:
            return 'closed'

    def setColumnValvePosition(self, position):
        if position == 'open':
            self.feg3.SetBeamValve(1)
        elif position == 'closed':
            self.feg3.SetBeamValve(0)
        else:
            raise ValueError

    # intensity is controlled by condenser lens 3
    def getIntensity(self):
        intensity, result = self.lens3.GetCL3()
        return float(intensity)/MAX

    def setIntensity(self, intensity, relative = 'absolute'):
        if relative == 'relative':
            intensity += self.getIntensity()
        elif relative == 'absolute':
            pass
        else:
            raise ValueError
        self._setIntensity(intensity)

    def _setIntensity(self, intensity):
        result = self.lens3.SetCL3(int(round(intensity*MAX)))
        
    def getDarkFieldMode(self):
        pass

    def setDarkFieldMode(self, mode):
        pass

    def getBeamBlank(self):
        bb, result = self.def3.GetBeamBlank()
        if bb == 0:
            return 'off'
        elif bb == 1:
            return 'on'
        else:
            raise SystemError

    def setBeamBlank(self, bb):
        if bb == 'off':
            result = self.def3.SetBeamBlank(0)
        elif bb == 'on':
            result = self.def3.SetBeamBlank(1)
        else:
            raise ValueError

    # the DiffractionStigmator of tecnai is the IntermediateStigmator of Jeol
    def getStigmator(self):
        c_x, c_y, result = self.def3.GetCLs()
        o_x, o_y, result = self.def3.GetOLs()
        d_x, d_y, result = self.def3.GetILs()
        return {"condenser": {"x": toLeginon(c_x), "y": toLeginon(c_y)},
            "objective": {"x": toLeginon(o_x), "y": toLeginon(o_y)},
            "diffraction": {"x": toLeginon(d_x), "y": toLeginon(d_y)}} 
 
    def setStigmator(self, stigs, relative = "absolute"):
        for key in stigs.keys():
            stigmators = self.getStigmator()
            if key == "condenser":
                stigmator = stigmators["condenser"]
            elif key == "objective":
                stigmator = stigmators["objective"]
            elif key == "diffraction":
                stigmator = stigmators["diffraction"]
            else:
                raise ValueError
            
            if relative == "relative":
                try:
                    stigs[key]["x"] += stigmator["x"]
                    stigs[key]["y"] += stigmator["y"]
                except KeyError:
                    pass
            elif relative == "absolute":
                pass
            else:
                raise ValueError

            try:
                stigmator["x"] = stigs[key]["x"]
                stigmator["y"] = stigs[key]["y"]
            except KeyError:
                pass

            if key == "condenser":
                result = self.def3.SetCLs(toJeol(stigmator["x"]), toJeol(stigmator["y"]))
            elif key == "objective":
                result = self.def3.SetOLs(toJeol(stigmator["x"]), toJeol(stigmator["y"]))
            elif key == "diffraction":
                result = self.def3.SetILs(toJeol(stigmator["x"]), toJeol(stigmator["y"]))
            else:
                raise ValueError
 
    def getSpotSize(self):
        spot_size, result = self.eos3.GetSpotSize()
        return spot_size + 1

    def setSpotSize(self, ss, relative = "absolute"):
        if relative == "relative":
            ss += self.getSpotSize()
        elif relative == "absolute":
            pass
        else:
            raise ValueError
 
        result = self.eos3.SelectSpotSize(ss - 1)
    
    def getBeamTilt(self):
        scale = self.getScale('beamtilt')
        neutral = self.getNeutral('beamtilt')
        raw={}
        out={}
        raw['x'], raw['y'], result = self.def3.GetCLA2()
        for axis in raw.keys():
            out[axis] = (raw[axis] - neutral[axis])*scale[axis]
        return out

    def setBeamTilt(self, vector, relative = "absolute"):
        scale = self.getScale('beamtilt')
        neutral = self.getNeutral('beamtilt')
        current_tilt = self.getBeamTilt()
        tilt = current_tilt.copy()
        if relative == 'relative':
            for axis in vector.keys():
                tilt[axis] += vector[axis]
        elif relative == 'absolute':
            for axis in vector.keys():
                tilt[axis] = vector[axis]
        else:
            raise ValueError

        raw_output={}
        raw_output['x'], raw_output['y'], result = self.def3.GetCLA2()
        for axis in vector.keys():
            raw_output[axis] = int(round(tilt[axis]/scale[axis]))+neutral[axis]

        result = self.def3.SetCLA2(raw_output['x'], raw_output['y'])

    def getBeamShift(self):
        scale = self.getScale('beamshift')
        neutral = self.getNeutral('beamshift')
        shift_x, shift_y, result = self.def3.GetCLA1()

        x = (shift_x - neutral['x'])*scale['x']
        y = (shift_y - neutral['y'])*scale['y']

        return {"x": x, "y": y}

    def setBeamShift(self, vector, relative = "absolute"):
        scale = self.getScale('beamshift')
        neutral = self.getNeutral('beamshift')
        current = self.getBeamShift()
        if relative == 'relative':
            if 'x' in vector:
                shift_x = vector['x'] + current['x']
            if 'y' in vector:
                shift_y = vector['y'] + current['y']
        elif relative == 'absolute':
            if 'x' in vector:
                shift_x = vector['x']
            if 'y' in vector:
                shift_y = vector['y']
        else:
            raise ValueError

        shift = current.copy()
        if relative == 'relative':
            for axis in vector.keys():
                shift[axis] += vector[axis]
        elif relative == 'absolute':
            for axis in vector.keys():
                shift[axis] = vector[axis]
        else:
            raise ValueError
        raw_output={}
        raw_output['x'], raw_output['y'], result = self.def3.GetCLA1()
        for axis in vector.keys():
            raw_output[axis] = int(round(shift[axis]/scale[axis]))+neutral[axis]

        result = self.def3.SetCLA1(raw_output['x'], raw_output['y'])
        if self.getJeolConfig('tem option','cl3_relaxation_mag') and self.relax_beam:
            self.relaxBeam()
 
    def getImageShift(self):
        scale = self.getScale('imageshift')
        neutral = self.getNeutral('imageshift')
        mode, name, result = self.eos3.GetFunctionMode() 
        if mode == FUNCTION_MODES['lowmag']:
            if self.getJeolConfig('tem option','use_pla'):
                shift_x, shift_y, result = self.def3.GetPLA()
            else:
                shift_x, shift_y, result = self.def3.GetIS1()
        elif mode == FUNCTION_MODES['mag1']:
            if self.getJeolConfig('tem option','use_pla'):
                shift_x, shift_y, result = self.def3.GetPLA()
            else:
                shift_x, shift_y, result = self.def3.GetIS1()
        else:
            raise RuntimeError('Image shift functions not implemented in this mode (%d, "%s")' % (mode, name))      
        result = {"x": (shift_x - neutral['x'])*scale['x'], "y": (shift_y - neutral['y'])*scale['y']}
        return result
    
    def setImageShift(self, vector, relative = "absolute"):
        scale = self.getScale('imageshift')
        neutral = self.getNeutral('imageshift')
        mode, name, result = self.eos3.GetFunctionMode() 
        current_shift = self.getImageShift()
        shift_x = current_shift['x']
        shift_y = current_shift['y']
        if relative == 'relative':
            if 'x' in vector:
                shift_x += vector['x']
            if 'y' in vector:
                shift_y += vector['y']
        elif relative == 'absolute':
            if 'x' in vector:
                shift_x = vector['x']
            if 'y' in vector:
                shift_y = vector['y']
        else:
            raise ValueError

        if self.getJeolConfig('tem option','use_pla'):
            result = self.def3.SetPLA(int(round((shift_x)/scale['x']))+neutral['x'], int(round((shift_y)/scale['y']))+neutral['y'])
            time.sleep(0.5)
        else:
            result = self.def3.SetIS1(int(round((shift_x)/scale['x']))+neutral['x'], int(round((shift_y)/scale['y']))+neutral['y'])

    def setFocusOLWithBeamShift(self, value):
        beam_shift_x, beam_shift_y, result = self.def3.GetCLA1()
        self.setRawFocusOL(value)
        result = self.def3.SetCLA1(beam_shift_x, beam_shift_y)

    def getFocus(self):
        scale = self.getScale('focus')
        mode, name, result = self.eos3.GetFunctionMode() 
        if mode == FUNCTION_MODES['lowmag']:
            raw_focus = self.getRawFocusOM()
        elif mode == FUNCTION_MODES['mag1']:
            raw_focus = self.getRawFocusOL()
        return scale*raw_focus

    def relaxBeam(self,steps=3,interval=0.1,totaltime=2):
        '''
        Emulate Lens Relaxation of CL3 in JEOL interface to stablize beam shift
        '''
        t0 = time.time()
        value_original = self.getIntensity()
        self.lens3.setNtrl(0)
        value_ntrl = self.getIntensity()
        # at least move 0.05 of the max scale
        full = max(abs(value_original - value_ntrl),0.05)
        diff = full / steps
        for i in range(3):
            magnitude = full - i * diff
            self._setIntensity(value_ntrl - magnitude)
            time.sleep(interval)
            self._setIntensity(value_ntrl + magnitude)
            time.sleep(interval)
        self._setIntensity(value_original)
        t = time.time()
        if t-t0 < totaltime:
            time.sleep(t-t0)
        return

    def setFocus(self, value):
        scale = self.getScale('focus')
        mode, name, result = self.eos3.GetFunctionMode()
        if mode == FUNCTION_MODES['lowmag']:
            self.setRawFocusOM(int(round(value/scale)))
        elif mode == FUNCTION_MODES['mag1']:
            # ZERO is when OLc=8000 hexa OLf=0000
            value = int(round(value/scale))
            self.setFocusOLWithBeamShift(value)
        else:
            raise RuntimeError('Focus functions not implemented in this mode (%d, "%s")' % (mode, name))

    def setRawFocusOM(self, value):
        self.lens3.SetOM(int(value))

    def getRawFocusOM(self):
        OM, result = self.lens3.GetOM()
        return OM

    def setRawFocusOL(self, value):
        OLc, OLf = self.toOLcOLf(value)
        self.lens3.SetOLc(OLc)
        self.lens3.SetOLf(OLf)

    def getRawFocusOL(self):
        OLf, result = self.lens3.GetOLf()
        OLc, result = self.lens3.GetOLc()
        OL = self.fromOLcOLf(OLc,OLf)
        return OL

    def getZeroDefocusOM(self):
        mag = self.getMagnification()
        zero_defocus_om = None
        if mag in self.zero_defocus_om.keys():
            zero_defocus_om = self.zero_defocus_om[mag]
        elif self.zero_defocus_om.keys():
            zero_defocus_om = self.zero_defocus_om[max(self.zero_defocus_om.keys())]
        return zero_defocus_om

    def setZeroDefocusOM(self):
        mag = self.getMagnification()
        if self.projection_submode_map[mag][0] != 'lowmag':
            return
        zero_defocus_om, result = self.lens3.GetOM()
        self.zero_defocus_om[mag] = zero_defocus_om
        return zero_defocus_om

    def getZeroDefocusOL(self):
        mag = self.getMagnification()
        zero_defocus_ol = None
        if mag in self.zero_defocus_ol.keys():
            zero_defocus_ol = self.zero_defocus_ol[mag]
        elif self.zero_defocus_ol.keys():
            zero_defocus_ol = self.zero_defocus_ol[max(self.zero_defocus_ol.keys())]
        return zero_defocus_ol

    def setZeroDefocusOL(self):
        mag = self.getMagnification()
        # set zero_defocus_ol only if it is a is in the range
        if self.projection_submode_map[mag][0] != 'mag1':
            debug_print('outside the mag range for zero defocus OL')
            return
        # set at the closest mag value but not higher
        items = self.zero_defocus_ol.items()
        ol_mags = self.zero_defocus_ol.keys()
        ol_mags.sort()
        while ol_mags:
            if mag >= int(ol_mags[-1]):
                break
            ol_mags.pop()
        if len(ol_mags):
            debug_print('zero_defocus set at %d' % (int(ol_mags[-1])))
            self.zero_defocus_ol[ol_mags[-1]] = self.getRawFocusOL()
        else:
            debug_print('zero_defocus no ol_mags set at %d' % (int(mag)))
            self.zero_defocus_ol['%d' % (int(mag),)] = self.getRawFocusOL()

    def getDefocus(self):
        scale = self.getScale('focus')
        mode, name, result = self.eos3.GetFunctionMode() 
        if mode == FUNCTION_MODES['lowmag']:
            OM = self.getRawFocusOM()
            zero_defocus_om = self.getZeroDefocusOM()
            return scale*(OM - zero_defocus_om)
        elif mode == FUNCTION_MODES['mag1']:
            OL = self.getRawFocusOL()
            zero_defocus_ol = self.getZeroDefocusOL()
            return scale*(OL - zero_defocus_ol)
        else:
            raise RuntimeError('Defocus functions not implemented in this mode (%d, "%s")' % (mode, name))

    def setDefocus(self, defocus, relative='absolute'):
        mode, name, result = self.eos3.GetFunctionMode()
        
        if defocus == 0.0:
            if relative == 'relative':
                return
            elif relative != 'absolute':
                raise ValueError
            elif mode == FUNCTION_MODES['lowmag']:
                self.lens3.SetOM(self.getZeroDefocusOM())
            elif mode == FUNCTION_MODES['mag1']:
                zero_defocus_ol = self.getZeroDefocusOL()
                self.setFocusOLWithBeamShift(zero_defocus_ol)
            else:
                raise RuntimeError('Defocus functions not implemented in this mode (%d, "%s")' % (mode, name))
            return
        
        scale = self.getScale('focus')
        if mode == FUNCTION_MODES['lowmag']:
            if relative == 'relative':
                defocus += self.getDefocus()
            elif relative != 'absolute':
                raise ValueError
            self.lens3.SetOM(self.getZeroDefocusOM() + int(round(defocus/scale)))
        elif mode == FUNCTION_MODES['mag1']:
            if relative == 'relative':
                raise RuntimeError('not implemented')
            elif relative == 'absolute':
                value = int(round(defocus/scale))
                zero_defocus_ol = self.getZeroDefocusOL()
                self.setFocusOLWithBeamShift(zero_defocus_ol + value)
            else:
                raise ValueError

        else:
            raise RuntimeError('Defocus functions not implemented in this mode (%d, "%s")' % (mode, name))

    def toOLcOLf(self,ticks):
        coarse_tick_addition = 0
        fine_ticks = ticks % COARSE_SCALE + ZERO + ZERO / COARSE_SCALE
        coarse_ticks = (ticks - fine_ticks) / COARSE_SCALE
        return coarse_ticks, fine_ticks

    def fromOLcOLf(self,OLc, OLf):
        return OLc * COARSE_SCALE + OLf

    def _resetDefocus(self):
        mode, name, result = self.eos3.GetFunctionMode() 
        if mode == FUNCTION_MODES['lowmag'] and not self.getZeroDefocusOM():
            self.setZeroDefocusOM()
        # only set if not set previously.  Does this mean it only get set once in a session ?
        elif mode == FUNCTION_MODES['mag1'] and not self.getZeroDefocusOL():
            self.setZeroDefocusOL()
    
    def resetDefocus(self):
        mode, name, result = self.eos3.GetFunctionMode() 
        if mode == FUNCTION_MODES['lowmag']:
            self.setZeroDefocusOM()
        elif mode == FUNCTION_MODES['mag1']:
            self.setZeroDefocusOL()
        else:
            raise RuntimeError('Defocus functions not implemented in this mode (%d, "%s")' % (mode, name))

    def _getMagnification(self):
        value, unit_str, label_str, result = self.eos3.GetMagValue()
        return value

    def getMagnification(self):
        mag = None
        trials = 0
        maxtrials = 10
        # repeat get since found on NYSBC 3200FSC that it may not return value on the first try
        while not mag:
            mag = self._getMagnification()
            if trials:
                debug_print('unsuccessful getMagnification(). trial %d' % (trials,)) 
                if trials > maxtrials:
                    raise RuntimeError('getMagnification abort after %d trials' % maxtrials)
            trials += 1
        return mag

    def getMainScreenMagnification(self):
        value, unit_str, label_str, result = self.eos3.GetMagValue()
        return value
        
    def getMagnifications(self):
        return self.magnifications

    def setMagnifications(self, mags):
        # This is called by EM node with magnifications list input
        self.magnifications = mags

        # This might be possible to be moved to somewhere else
        if self.projection_submode_map:
            # set zero defocus for current mag mode only
            self._resetDefocus()
    
    def setMagnificationsFromProjectionSubModes(self):
        '''
        Make a sorted magnifications list
        '''
        mode_map = self.getProjectionSubModeMap()
        mags = mode_map.keys()
        mags.sort()
        if self.magnifications and mags == self.magnifications:
            # do not duplicate if exists already
            return
        self.magnifications = mags

    def getMagnificationsInitialized(self):
        if self.magnifications:
            return True
        else:
            return False

    def findMagnifications(self):
        '''
        Go through magnifications to register magnifications.
        '''
        # One of the first functions to run during installation to get valid magnification values
        savedmode, name, result = self.eos3.GetFunctionMode()
        savedmag, unit_str, label_str, result = self.eos3.GetMagValue()

        if savedmode not in (FUNCTION_MODES['lowmag'],FUNCTION_MODES['mag1']):
            raise ValueError('Current function mode %s not implemented' % name)
        mags = {}
        overwritten_mags = []
        # Iterating mode_name in the order stated in 'use_modes' of jeol.cfg means that
        # the name lists later will be used to overwrite a duplicated mag.
        for mode_name in self.getJeolConfig('eos','use_modes'):
            mode_index = FUNCTION_MODES[mode_name]
            self.eos3.SelectFunctionMode(mode_index)
            mags[mode_index] = []
            mag_index=0
            while True:
                overwritten = False
                self.eos3.SetSelector(mag_index)
                magvalue = self.eos3.GetMagValue()
                mag = magvalue[0]
                # no error is returned when index is out of range.  The mag just
                # does not change.
                if mag not in mags[mode_index]:
                    mags[mode_index].append(mag)
                    # overwrite is set to true so that mag1 mag overwrite the ones in lowmag if
                    # at the sam mag.
                    overwritten = self.addProjectionSubModeMap(mag,mode_name,mode_index,overwrite=True)
                    if overwritten is True:
                        overwritten_mags.append((mode_index,mag))
                    mag_index += 1
                else:
                    # end of this projection submode
                    break
        # remove mags above the mag that is overwritten because they will not index correctly.
        self.removeBrokenMags(overwritten_mags)

        # set magnifications now that self.projection_submode_map is set
        self.setMagnificationsFromProjectionSubModes()
        self.setProjectionSubModeMags()
        # return to the original mag
        self.setMagnification(savedmag)

    def removeBrokenMags(self, overwritten_mags):
        if len(overwritten_mags) == 0:
            return
        for overwritten_mag_tuple in overwritten_mags:
            mode_index, mag_cutoff = overwritten_mag_tuple
            for lower_mode_index in range(mode_index):
                for mag,submode_info in self.projection_submode_map.items():
                    if mag >= mag_cutoff and submode_info[1] == lower_mode_index:
                        del self.projection_submode[mag]

    def getMagnificationIndex(self, magnification=None):
        if magnification is None:
            magnification = self._getMagnification()
        try:
            return self.magnifications.index(magnification)
        except ValueError:
            raise ValueError('invalid magnification, must be in {}'.format(self.magnifications))

    def setMagnificationIndex(self, value):
        if value <= len(self.magnifications):
            return self.setMagnification(self.magnifications[value])
        else:
            raise ValueError('invalid magnification, must be in {}'.format(self.magnifications))

    def calculateSelectorIndex(self, mode_index, mag):
        return self.submode_mags[mode_index].index(mag)

    def setMagnification(self, value):
        '''
        Set Magnification by value string or number
        '''
        try:
            value = int(round(value))
        except TypeError:
            # magnification value from choice string selection is a string
            try:
                value = int(value)
            except:
                raise TypeError
    
        if value not in self.projection_submode_map.keys():
            raise ValueError

        if not self.submode_mags:
            raise RuntimeError
        
        current_mag = self.getMagnification()

        old_mode_index, name, result = self.eos3.GetFunctionMode()
        new_mode_name = self.projection_submode_map[value][0]
        new_mode_index = self.projection_submode_map[value][1]
        result = self.eos3.SelectFunctionMode(new_mode_index)
        if new_mode_index == FUNCTION_MODES['lowmag'] and old_mode_index != FUNCTION_MODES['lowmag']:
                #set to an arbitrary low mag to remove distortion
                relax_mag = self.submode_mags[FUNCTION_MODES['lowmag']][-1]
                self.eos3.SetSelector(self.calculateSelectorIndex(new_mode_index, relax_mag))
                time.sleep(1)
        self.eos3.SetSelector(self.calculateSelectorIndex(new_mode_index, value))

        debug_print('relaxation current mag %d' % current_mag)
        debug_print('relaxation target mag %d' % value)
        if self.getJeolConfig('tem option','cl3_relaxation_mag') and value != current_mag and value > self.getJeolConfig('tem option','cl3_relaxation_mag'):
            debug_print('need relaxing')
            self.relax_beam = True
        else:
            self.relax_beam = False

        self._resetDefocus()
        return

    def getProjectionSubModeIndex(self):
        mode_index, name, result = self.eos3.GetFunctionMode()
        return mode_index

    def getProjectionSubModeName(self):
        mode_index, name, result = self.eos3.GetFunctionMode()
        # can not return name because both 0 and 1 index function mode returns 'mag' as name.
        return FUNCTION_MODE_ORDERED_NAMES[mode_index]

    def getLensSeriesDivision(self,mag):
        mode_name,mode_id = self.projection_submode_map[mag]
        # depends on mag to choose ['ls1','ls2','ls3'...,'lm1']
        mode_subname = self.subDivideMode(mode_name,mag)
        return mode_subname

    def getStagePosition(self):
        scale = self.getScale('stage')
        x, y, z, a, b, result = self.stage3.GetPos()
        position = {
            'x' : x/scale['x'],
            'y' : y/scale['y'],
            'z' : z/scale['z'],
            'a' : math.radians(a),
            'b' : math.radians(b)
        }
        return position

    def _isStageMoving(self):
        # check if stage is moving
        x, y, z, tx, ty, result = self.stage3.GetStatus()
        return x or y or z or tx or ty

    def _waitForStage(self,sleeptime=0.1):
        # wait for stage to stop moving
        while self._isStageMoving():
            time.sleep(sleeptime)

    def printPosition(self, tag, p):
        pr = {}
        for axis in ('x','y','a'):
            if axis not in p.keys():
                pr[axis] = '     '
            else:
                pr[axis] = '%5.1f' % (p[axis]*1e6)
        if DEBUG:
            debug_print(tag+' '+pr['x']+','+pr['y']+','+pr['a'])

    def reducedStageBacklashCorrection(self, current_position, position):
        '''
        Reduced backlash Correction at half of the shift distance at each axis.
        '''
        tmp_position = current_position.copy()
        has_changed = False
        for axis in position.keys():
            if axis not in ('x','y'):
                continue
            shift = current_position[axis]-position[axis]
            if abs(shift) > self.backlash_limit['reduced']:
                # shift to half the distance as tmp_position
                #shift_sign = int(shift/abs(shift))
                shift_sign = 1
                tmp_position[axis] = -shift_sign*0.5*shift + position[axis]
                has_changed = True
        if has_changed:
            debug_print('set to tmp_position in reduced backlash correction')
            self._setStageXY(tmp_position)
            time.sleep(self.backlash_pause)

    def fullStageBacklashCorrection(self, current_position, position):
        '''
        Stage Backlash Correction as implemented in JEM Instrument
        Position Module
        '''
        tmp_position = {}
        for axis in position.keys():
            if axis not in ('x','y'):
                continue

            if True:
                #shift_sign = int(shift/abs(shift))
                shift_sign = 1
                tmp_position[axis] = shift_sign * self.backlash_scale[axis] + position[axis]
        self.printPosition('backlash',tmp_position)
        if tmp_position:
            debug_print('correcting backlash')
            self._setStageXY(tmp_position)
            time.sleep(self.backlash_pause)

    def setStagePosition(self, position, relative='absolute', backlash=True):
        # move relative or absolute, add current position for relative
        if relative == 'relative':
            current_position = self.getStagePosition()
            for axis in position:
                try:
                    position[axis] += current_position[axis]
                except KeyError:
                    pass
        elif relative == 'absolute':
            pass
        else:
            raise ValueError

        # set non backlash axis first
        self.setStageZ(position)
        self.setStageAB(position)

        self.setStageXY(position)

    def setStageXY(self, position):
        if not set(('x','y')).intersection(position.keys()):
            return
        pos = position.copy()
        for axis in ('x','y'):
            if axis not in pos:
                pos[axis] = self.getStagePosition()[axis]
                continue
            if abs(pos[axis]) > self.stage_limit[axis]:
                raise ValueError('%s limit reached. Ignore' % axis)
        # set axes that need backlash correction
        backlash = True
        if backlash:
            current_position = self.getStagePosition()
            shift = math.hypot(current_position['x']-pos['x'],current_position['y']-pos['y'])
            if shift > self.backlash_limit['full']:
                self.fullStageBacklashCorrection(current_position,pos)
            elif shift > self.backlash_limit['reduced']:
                self.reducedStageBacklashCorrection(current_position, pos)
        self._setStageXthenY(pos)
        #self.confirmStagePosition(pos,'xy')

    def confirmStagePosition(self, position, axes='z'):
        # JEM stage call may return without giving error when the position is not reached.
        # Noticed this at NYSBC JEM-2100f
        # Make it to retry.
        accuracy = self.getJeolConfig('stage','accuracy')
        new_position = self.getStagePosition()

        # check axes character by character
        for axis in axes:
            if axis in position.keys() and abs(new_position[axis] - position[axis]) > accuracy[axis]:
                self.printPosition('new', new_position)
                self.printPosition('target', position)
                debug_print('stage %s not reached' % axis)
                axis_position = {axis:position[axis]}
                self.setStagePositionByAxis(position,axis)
            else:
                debug_print('stage %s reached' % axis)

    def setStagePositionByAxis(self, position, axis):
        keys = position.keys()
        if axis not in keys:
            return
        if axis in ('a','b'):
            self._setStageAB(position,axis)
        elif axis == 'z':
            self._setStageZ(position)
        else:
            self._setStageXthenY(position)

    def setStageZ(self, position):
        if 'z' not in position:
            return
        # limit check
        if abs(position['z']) > self.stage_limit['z']:
            raise ValueError('z limit reached. Ignore')
        self._setStageZ(position)

    def _setStageZ(self, position):
        '''
        set stage in z. position must be in range and has z value.
        '''
        scale = self.getScale('stage')
        p = {'z':position['z']}
        result = self.stage3.SetZ(p['z']*scale['z'])
        self._waitForStage()
        self.confirmStagePosition(p,('z',))

    def setStageAB(self, position):
        if 'a' not in position and 'b' not in position:
            return
        for axis in ('a','b'):
            if axis not in position:
                continue
            if abs(position[axis]) > self.stage_limit[axis]:
                raise ValueError('%s limit reached. Ignore' % axis)
            self._setStageAB(position,axis)
    
    def _setStageAB(self, position, axis='a'):
        '''
        set stage A or B. Must be within limit
        '''
        scale = self.getScale('stage')
        # set stage position and wait for movement to stop
        angle_axes = {'a':'x','b':'y'}
        attr = getattr(self.stage3,'SetTilt%sAngle' % angle_axes[axis])
        result = attr(math.degrees(position['a']))
        self._waitForStage()
        # on JEM2100F isStageMoving gives false all the time in alpha since the motor moves fast but not accrurately.  Must confirm
        self.confirmStagePosition(position,'a')

    def _setStageXY(self, position):
        '''
        Set stage in xy direction and then wait to stop.
        This makes it move in diagonal direction.
        Position must have both xy axis values and within limit.
        '''
        scale = self.getScale('stage')
        if self.hasPiezoStage():
            debug_print('reset piezo')
            self.resetPiezoPosition()
            # Somehow scale is ten times bigger internally at the scope at this point
            scale = {'x':scale['x']/10.0,'y':scale['y']/10.0}
        self.printPosition('_setXY', position)
        raw_position={'x':position['x']*scale['x'],'y':position['y']*scale['y']}
        result = self.stage3.SetX(raw_position['x'])
        result = self.stage3.SetY(raw_position['y'])
        self._waitForStage()

    def _setStageXthenY(self, position):
        '''
        Set stage in x direction wait to stop and then to y direction.
        The movement is therefore zigzag.
        position can have only one key
        '''
        self.printPosition('_setXthenY', position)
        scale = self.getScale('stage')
        if 'x' in position.keys():
            raw_position=position['x']*scale['x']
            result = self.stage3.SetX(raw_position)
            self._waitForStage()
        if 'y' in position.keys():
            raw_position=position['y']*scale['y']
            result = self.stage3.SetY(raw_position)
            self._waitForStage()

    def hasPiezoStage(self):
        #return self.getJeolConfig('stage','use_piezo')
        return False

    """
    def getPiezoPosition(self):
        # TO DO put this in jeol.com as 'piezo'
        scale = self.getScale('stage')
        x, y, result = self.stage3.GetPiezoPosi()
        position = {
            'x' : x/scale['x'],
            'y' : y/scale['y'],
        }
        self.printPosition('got',position)
        return position

    def setPiezoPosition(self, position, relative = 'absolute'):
        # move relative or absolute, add current position for relative
        if relative == 'relative':
            current_position = self.getPiezoPosition()
            for axis in position:
                try:
                    position[axis] += current_position[axis]
                except KeyError:
                    pass
        elif relative == 'absolute':
            pass
        else:
            raise ValueError

        # limit check
        limit = self.getLimit('piezo')
        for axis in ('x','y'):
            if axis in position and abs(position[axis]) > limit[axis]:
                raise ValueError('%s limit reached. Ignore' % axis)
        
        debug_print('piezo target %s' % (position,))
        # set axes that need backlash correction
        self._setPiezoPosition(position)

    def _setPiezoPosition(self, position):
        status = self.stage3.selDrvMode(1)
        time.sleep(0.5)
        if status != 0:
            raise RuntimeError('No PiezoStage')
        scale = self.getScale('stage')
        for axis in ('x','y'):
            if axis not in position:
                position[axis] = self.getPiezoPosition()[axis]
        raw_position=(position['x']*scale['x'],position['y']*scale['y'])
        #result = self.stage3.SetPosition(raw_position[0],raw_position[1])
        debug_print('%s' % (raw_position,))
        result = self.stage3.SetX(raw_position[0])
        result = self.stage3.SetY(raw_position[1])
        self._waitForStage()
        for i in range(30):
            p = self.getPiezoPosition()
            deltax = abs(p['x'] - position['x'])
            deltay = abs(p['y']-position['y'])
            if deltax < 3e-8 and deltay < 3e-8:
                break
            self.stage3.selDrvMode(1)
            result = self.stage3.SetX(raw_position[0])
            result = self.stage3.SetY(raw_position[1])
            #self._waitForStage()
            time.sleep(0.5)
        debug_print('set DriveBack')
        status = self.stage3.selDrvMode(0)
        time.sleep(0.5)

    def resetPiezoPosition(self):
        self._setPiezoPosition({'x':0.0,'y':0.0})

    def refreshPiezoStage(self):
        '''
        similar to SF refresh
        '''
        limit = self.getLimit('piezo')
        old_position=self.getPiezoPosition()
        self._setPiezoPosition({'x':-limit['x'],'y':-limit['y']})
        time.sleep(0.5)
        self.resetPiezoPosition()
        # TODO should only move if not close    
        self._setPiezoPosition(old_position)
    """

    def getLowDoseStates(self):
        return ['on', 'off', 'disabled']
    
    def getLowDose(self):
        mode, result = self.mds3.GetMdsMode()
        if mode == MDS_OFF: 
            return 'off'
        elif mode in (MDS_SEARCH, MDS_FOCUS, MDS_PHOTO):
            return 'on'
        else:
            return 'disabled'
 
    def setLowDose(self, ld):
        if ld == 'off':
            result = self.mds3.EndMDSMode()
        elif ld == 'on':
            result = self.mds3.SetSearchMode()
        else:       
            raise ValueError

    def getLowDoseModes(self):
        return ['exposure', 'focus1', 'search', 'unknown', 'disabled']
        
    def getLowDoseMode(self):
        mode, result = self.mds3.GetMdsMode()
        if mode == MDS_OFF:
            return 'disabled'
        elif mode == MDS_SEARCH:
            return 'search'
        elif mode == MDS_FOCUS:
            return 'focus1'
        elif mode == MDS_PHOTO:
            return 'exposure'
        else:
            return 'unknown'

    def setLowDoseMode(self, mode):
        if mode == 'exposure':
            result = self.mds3.SetPhotosetMode()
        elif mode == 'focus1':
            result = self.mds3.SetFocusMode()
        elif mode == 'search':
            result = self.mds3.SetSearchMode()
        elif mode == 'disabled':
            result = self.mds3.EndMdsMode()
        else:
            raise ValueError
   
    def getDiffractionMode(self):
        mode, result = self.eos3.GetFunctionMode()
        if mode in (FUNCTION_MODES['lowmag'], FUNCTION_MODES['mag1']):
            return "imaging"
        elif mode == FUNCTION_MODES['diff']:
            return "diffraction"
        else:
            raise SystemError("getDiffractionMode")

    def setDiffractionMode(self, mode):
        if mode == "imaging":
            result = self.eos3.SelectFunctionMode(FUNCTION_MODES['mag1'])
        elif mode == "diffraction":
            result = self.eos3.SelectFunctionMode(FUNCTION_MODES['diff'])
        else:
            raise ValueError("Unknown value for setDiffractionmode:".format(mode))
        return 0

    def getScreenCurrent(self):
        value, result = self.camera3.GetCurrentDensity()
        return value*self.getJeolConfig('camera','current_density_scale')

    def getMainScreenPositions(self):
        return ['up', 'down', 'unknown']
        
    def getMainScreenPosition(self):
        position, result = self.detector3.GetPosition(MAIN_SCREEN)
        if position == 1:
            return 'down'
        else:
            return 'up'

    def setMainScreenPosition(self, position):
        if position == 'up':
            result = self.detector3.SetPosition(MAIN_SCREEN, 0)
        elif position == 'down':
            result = self.detector3.SetPosition(MAIN_SCREEN, 1)
        else:
            raise ValueError

    def getEnergyFiltered(self):
        return self.getJeolConfig('tem option','energy_filter')

    def getEnergyFilter(self):
        position, result = self.filter3.GetSlitPosition()
        return bool(position)

    def setEnergyFilter(self, value):
        if value:
            result = self.filter3.SetSlitPosition(1)
        else:
            result = self.filter3.SetSlitPosition(0)

    def getEnergyFilterWidth(self):
        width, result = self.filter3.GetSlitWidth()
        return width

    def setEnergyFilterWidth(self, value):
        result = self.filter3.SetSlitWidth(value)

    def alignEnergyFilterZeroLossPeak(self):
        pass

    def getApertures(self):
        return ['condenser', 'objective', 'high contrast', 'selected area']

    def _getApertureKind(self, name):
        if name == 'condenser':
            return CLA
        elif name == 'objective':
            return OLA
        elif name == 'high contrast':
            return HCA
        elif name == 'selected area':
            return SAA
        else:
            raise ValueError('Invalid aperture name specified')

    def _getApertureSizesOfKind(self, name):
        if name == 'condenser':
            return self.getJeolConfig('apt','cla_sizes')
        elif name == 'objective':
            return self.getJeolConfig('apt','ola_sizes')
        elif name == 'high contrast':
            return self.getJeolConfig('apt','hca_sizes')
        elif name == 'selected area':
            return self.getJeolConfig('apt','saa_sizes')
        else:
            raise ValueError('Invalid aperture name specified')


    def getApertureSizes(self):
        sizes = {}

        names = self.getApertures()

        for name in names:
            sizes[name] = self._getApertureSizesOfKind(name)

        return sizes

    def getApertureSize(self):
        '''
        get current aperture size of each kind.  Returns
        a dictionary with the name as the key and the size
        in meters as the item
        '''
        sizes = {}

        positions = self.getAperturePosition()
        for name in positions.keys():
            size_list = self._getApertureSizesOfKind(name)

        for name in names:
            kind = self._getApertureKind(name)
            # Despite the name, this gives not the size
            # but a number as the current aperture position
            if not self.has_auto_apt:
                index = 0
            else:
                index, result = self.apt3.GetSize(kind)

                for i in range(10):
                    if result != 0:
                        time.sleep(.1)
                        size, result = self.apt3.GetSize(kind)

                if result != 0:
                    raise SystemError('Get %s aperture size failed' % name)

                size_list = self._getApertureSizes(name)

            try:
                sizes[name] = size_list[positions[name]]
            except ValueError:
                raise SystemError('No %s aperture size for index %d' % (name,index))

        return sizes

    def setApertureSize(self, sizes):
        if not self.has_auto_apt:
            return

        current_kind, result = self.apt3.GetKind()

        for name in sizes:
            kind = self._getApertureKind(name)

            size_list = self._getApertureSizesOfKind(name)

            if sizes[name] is None:
                return

            try:
                index = size_list.index(sizes[name])
            except ValueError:
                raise ValueError('Invalid %s aperture size %d specified' % (name, sizes[name]))

            current_index, result = self.apt3.GetSize(kind)
            for i in range(10):
                if result != 0:
                    time.sleep(.1)
                    current_index, result = self.apt3.GetSize(kind)

            if result != 0:
                raise SystemError('Get %s aperture size failed' % name)
            if index != current_index:

                result = self.apt3.SelectKind(kind)

                if current_index > index:
                    result = self.apt3.SetSize(index - 1)
                    result = None
                    # should add timeout
                    while result != 0:
                        set_index, result = self.apt3.GetSize(kind)
                        time.sleep(.1)

                result = self.apt3.SetSize(index)
                result = None
                # should add timeout
                while result != 0:
                    set_index, result = self.apt3.GetSize(kind)
                    time.sleep(.1)

        result = self.apt3.SelectKind(current_kind)

    def getAperturePosition(self):
        positions = {}

        names = self.getApertures()

        if not self.has_auto_apt:
            for name in names:
                positions[name] = 0
            return positions

        current_kind, result = self.apt3.GetKind()

        for name in names:
            kind = self._getApertureKind(name)

            result = self.apt3.SelectKind(kind)

            x, y, result = self.apt3.GetPosition()
            for i in range(10):
                if result != 0:
                    time.sleep(.1)
                    x, y, result = self.apt3.GetPosition()

            if result != 0:
                raise SystemError('Get %s aperture position failed' % name)

            positions[name] = {'x': x, 'y': y}

        result = self.apt3.SelectKind(current_kind)

        return positions

    def setAperturePosition(self, positions):
        if not self.has_auto_apt:
            return

        current_kind, result = self.apt3.GetKind()
        for name in positions:
            p = positions[name]
            if 'x' in p and type(p['x']) is not int:
                raise TypeError
            if 'y' in p and type(p['y']) is not int:
                raise TypeError
            

            kind = self._getApertureKind(name)

            result = self.apt3.SelectKind(kind)

            x, y, result = self.apt3.GetPosition()

            if 'x' in p and p['x'] != x or 'y' in p and p['y'] != y:
                result = self.apt3.SetPosition(p['x'], p['y'])

        result = self.apt3.SelectKind(current_kind)

    def _setSpecialMag(self):
        result = self.eos3.SelectFunctionMode(FUNCTION_MODES['mag1'])
        result = self.lens3.SetOLc(12646)
        result = self.lens3.SetOLf(34439)
        result = self.lens3.SetOM(41801)

    '''
    Camera function list
        ::TakePhoto 
        ::CancelPhoto 
        ::SetExpTime
        ::GetExpTime
        ::SelectFilmLoadingMode - 0 : manual operation / 1 : auto operation 1 / 2 : auto operation 2
        ::GetShutterMode        - Shutter modes are
        ::SetShutterMode        - 0 : manual exposure / 1 : automatic exposure / 2 : bulb
        ::GetShutterPosition    - Shutter positions are
        ::SetShutterPosition    - 0 : open / 1 : close / 2 : exposure
        ::ExposeShutter
    ''' 
    def getCameraStatus(self):
        status, result = self.camera3.GetStatus()
        return status

    def setFilmLoadingMode(self, feed = 0):
        result = self.camera3.SelectFilmLoadingMode(feed)

    def takePhoto(self):
        result = self.camera3.TakePhoto()

    def cancelPhoto(self):
        result = self.camera3.CancelPhoto()

    def getExposeTime(self):
        time, result = self.camera3.GetExpTime()
        return time

    def setExposeTime(self, time):
        result = self.camera3.SetExpTime(time)

    def preFilmExposure(self, value):
        if not value:
            return
        value, result = self.camera3.GetUnused()
        if value < 1:
            raise RuntimeError('No film to take exposure')

        self.camera3.LoadFilm()
        time.sleep(6)
        
        return

    def postFilmExposure(self, value):
        if not value:
            return
        result = self.camera3.EjectFilm()
        return

    def exposeSpecimenNotCamera(self,exptime=0):
        if exptime == 0:
            return
        self.setMainScreenPosition('down')
        time.sleep(exptime)
        self.setMainScreenPosition('up')

    def setFunctionMode(self, mode):
        if mode not in FUNCTION_MODE.keys():
            raise ValueError("Unknown function mode", mode)
        result = self.eos3.SelectFunctionMode(FUNCTION_MODES[mode])

    def getFunctionMode(self):
        mode, name, result = self.eos3.GetFunctionMode()
        return FUNCTION_MODE_ORDERED_NAMES[mode]
