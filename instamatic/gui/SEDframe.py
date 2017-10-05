from Tkinter import *
from ttk import *
import tkMessageBox
import os, sys

import matplotlib
matplotlib.use('TkAgg')
from instamatic.calibrate import CalibBeamShift, CalibDirectBeam
from instamatic.calibrate.filenames import CALIB_DIRECTBEAM, CALIB_BEAMSHIFT

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

        self.calib_path = ""

        self.init_vars()

        Label(self, text="Scan area (um)").grid(row=5, column=0)
        self.e_start_x = Entry(self, width=20, textvariable=self.var_scan_area)
        self.e_start_x.grid(row=5, column=1)

        self.CollectionButton = Button(self, text="Start Collection", command=self.start_collection, state=NORMAL)
        self.CollectionButton.grid(row=10, column=0)

        self.ShowCalibBeamshift = Button(self, text="Show calib beamshift", command=self.show_calib_beamshift, state=NORMAL)
        self.ShowCalibBeamshift.grid(row=9, column=0)

        self.ShowCalibDirectBeam1 = Button(self, text="Show calib directbeam1", command=self.show_calib_directbeam1, state=NORMAL)
        self.ShowCalibDirectBeam1.grid(row=9, column=1)
        
        self.ShowCalibDirectBeam2 = Button(self, text="Show calib directbeam2", command=self.show_calib_directbeam2, state=NORMAL)
        self.ShowCalibDirectBeam2.grid(row=9, column=2)

    def init_vars(self):
        self.var_scan_area = DoubleVar(value=100)

    def set_trigger(self, trigger=None):
        self.triggerEvent = trigger

    def set_events(self, startEvent=None,
                         stopEvent=None):
        self.startEvent = startEvent
        self.stopEvent = stopEvent

    def start_collection(self):
        print "Start button pressed"
        okay = tkMessageBox.askokcancel("Start experiment", message3, icon='warning')
        if okay:
            self.startEvent.set()
            self.triggerEvent.set()

    def stop_collection(self):
        print "Stop button pressed"
        self.stopEvent.set()

    def show_calib_beamshift(self):
        path = os.path.join(self.calib_path, CALIB_BEAMSHIFT)
        c = CalibDirectBeam.from_file(path)
        c.plot()

    def show_calib_directbeam1(self):
        path = os.path.join(self.calib_path, CALIB_DIRECTBEAM)
        c = CalibDirectBeam.from_file(path)
        c.plot("DiffShift")

    def show_calib_directbeam2(self):
        path = os.path.join(self.calib_path, CALIB_DIRECTBEAM)
        c = CalibDirectBeam.from_file(path)
        c.plot("BeamShift")

    def get_scan_area(self):
        return self.var_scan_area.get()


if __name__ == '__main__':
    root = Tk()
    ExperimentalSED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

