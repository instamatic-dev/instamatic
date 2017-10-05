from Tkinter import *
import tkMessageBox
import numpy as np
from PIL import Image, ImageTk

import matplotlib
matplotlib.use('TkAgg')
from instamatic.calibrate import CalibBeamShift, CalibDirectBeam



message1 = """
 1. Go to diffraction mode and select desired camera length (CAM L)
 2. Center the beam with diffraction shift (PLA)
 3. Focus the diffraction pattern (DIFF FOCUS)
    
Press <OK> to start"""

message2 = """
 1. Go to desired magnification (e.g. 2500x)
 2. Select desired beam size (BRIGHTNESS)
 3. Center the beam with beamshift
    
Press <OK> to start"""

message3 = """
 1. Move the stage to where you want to begin

Press <OK> to start"""

class ExperimentalSED(object, LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Serial electron diffraction")
        self.parent = parent

        self.directbeam_calibration = None
        self.beamshift_calibration = None

        self.init_vars()

        Label(self, text="Stage position (XY)").grid(row=4, column=0)
        self.e_start_x = Entry(self, width=20, textvariable=self.var_start_x)
        self.e_start_y = Entry(self, width=20, textvariable=self.var_start_y)
        self.e_start_x.grid(row=4, column=1)
        self.e_start_y.grid(row=4, column=2)

        self.SetStartButton = Button(self, text="Set", command=self.setStartPosition, anchor=W)
        self.SetStartButton.grid(row=4 , column=3)

        Label(self, text="Scan area (um)").grid(row=5, column=0)
        self.e_start_x = Entry(self, width=20, textvariable=self.var_scan_area)
        self.e_start_x.grid(row=5, column=1)

        self.CollectionButton = Button(self, text="Start Collection", command=self.start_collection, anchor=W, state=DISABLED)
        self.CollectionButton.grid(row=10, column=0)

        self.CalibBeamshift = Button(self, text="Calib Beamshift", command=self.calib_beamshift, anchor=W, state=NORMAL)
        self.CalibBeamshift.grid(row=8, column=0)

        self.ShowCalibBeamshift = Button(self, text="Show calib", command=self.show_calib_beamshift, anchor=W, state=DISABLED)
        self.ShowCalibBeamshift.grid(row=8, column=1)

        self.CalibDirectBeam = Button(self, text="Calib Direct beam", command=self.calib_directbeam, anchor=W, state=NORMAL)
        self.CalibDirectBeam.grid(row=9, column=0)

        self.ShowCalibDirectBeam1 = Button(self, text="Show calib", command=self.show_calib_directbeam1, anchor=W, state=DISABLED)
        self.ShowCalibDirectBeam1.grid(row=9, column=1)
        
        self.ShowCalibDirectBeam2 = Button(self, text="Show calib", command=self.show_calib_directbeam2, anchor=W, state=DISABLED)
        self.ShowCalibDirectBeam2.grid(row=9, column=2)

    def init_vars(self):
        self.var_start_x = DoubleVar(value=0)
        self.var_start_y = DoubleVar(value=0)
        self.var_scan_area = DoubleVar(value=100)

    def set_trigger(self, trigger=None):
        self.triggerEvent = trigger

    def set_events(self, startEvent=None,
                         stopEvent=None,
                         start_calib_directbeam=None,
                         stop_calib_directbeam=None,
                         start_calib_beamshift=None,
                         stop_calib_beamshift=None):

        self.startEvent = startEvent
        self.stopEvent = stopEvent
        self.start_calib_directbeam = start_calib_directbeam
        self.stop_calib_directbeam = stop_calib_directbeam
        self.start_calib_beamshift = start_calib_beamshift
        self.stop_calib_beamshift = stop_calib_beamshift

    def start_collection(self):
        print "Start button pressed"
        okay = tkMessageBox.askokcancel("Start experiment", message3, icon='warning')
        if okay:
            self.startEvent.set()
            self.triggerEvent.set()

    def stop_collection(self):
        print "Stop button pressed"
        self.stopEvent.set()

    def setStartPosition(self):
        x,y  = self.ctrl.xy
        self.var_start_x.set(x)
        self.var_start_y.set(y)

    def show_calib_beamshift(self):
        c = self.beamshift_calibration
        if not c:
            return
        c.plot()

    def calib_beamshift(self):
        okay = tkMessageBox.askokcancel("Calibrate beamshift", message1, icon='warning')
        if okay:
            self.start_calib_beamshift.set()
            self.triggerEvent.set()
        self.ShowCalibBeamshift.config(state=NORMAL)
        if self.directbeam_calibration:
            self.CollectionButton.config(state=NORMAL)

    def show_calib_directbeam1(self):
        c = self.directbeam_calibration
        if not c:
            return
        c.plot("DiffShift")

    def show_calib_directbeam2(self):
        c = self.directbeam_calibration
        if not c:
            return
        c.plot("BeamShift")

    def calib_directbeam(self):
        okay = tkMessageBox.askokcancel("Calibrate directbeam", message2, icon='warning')
        if okay:
            self.start_calib_directbeam.set()
            self.triggerEvent.set()
        self.ShowCalibDirectBeam1.config(state=NORMAL)
        self.ShowCalibDirectBeam2.config(state=NORMAL)
        if self.beamshift_calibration:
            self.CollectionButton.config(state=NORMAL)

    def get_scan_area(self):
        return self.var_scan_area.get()


if __name__ == '__main__':
    root = Tk()
    ExperimentalSED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

