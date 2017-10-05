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
 2. Follow the instructions in the terminal

Press <OK> to start"""

class ExperimentalSED(object, LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Serial electron diffraction")
        self.parent = parent

        self.calib_path = ""

        self.init_vars()

        frame = Frame(self)

        Label(frame, text="Scan area (um)").grid(row=5, column=0, sticky="W")
        self.e_start_x = Entry(frame, width=20, textvariable=self.var_scan_area)
        self.e_start_x.grid(row=5, column=1)

        frame.pack(side="top", fill="x", padx=10)

        frame = Frame(self)        
        self.ShowCalibBeamshift = Button(frame, text="Show calib beamshift", command=self.show_calib_beamshift, state=NORMAL)
        self.ShowCalibBeamshift.pack(side="left", expand=True, fill="x", padx=10)

        self.ShowCalibDirectBeam1 = Button(frame, text="Show calib directbeam1", command=self.show_calib_directbeam1, state=NORMAL)
        self.ShowCalibDirectBeam1.pack(side="left", expand=True, fill="x", padx=10)

        self.ShowCalibDirectBeam2 = Button(frame, text="Show calib directbeam2", command=self.show_calib_directbeam2, state=NORMAL)
        self.ShowCalibDirectBeam2.pack(side="left", expand=True, fill="x", padx=10)
        frame.pack(side="top", fill="both", expand=True)

        frame = Frame(self)

        self.CollectionButton = Button(frame, text="Start Collection", command=self.start_collection, state=NORMAL)
        self.CollectionButton.pack(side="bottom", fill="both")

        frame.pack(side="bottom", fill="both", padx=10, pady=10)

    def init_vars(self):
        self.var_scan_area = DoubleVar(value=100)

    def set_trigger(self, trigger=None):
        self.triggerEvent = trigger

    def set_events(self, startEvent=None,
                         stopEvent=None):
        self.startEvent = startEvent
        self.stopEvent = stopEvent

    def start_collection(self):
        okay = tkMessageBox.askokcancel("Start experiment", message3, icon='warning')
        if okay:
            self.startEvent.set()
            self.triggerEvent.set()

    def stop_collection(self):
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

