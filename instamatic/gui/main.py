#!/usr/bin/env python

from Tkinter import *
from tkFileDialog import *
import tkMessageBox
from ttk import *
import os

import numpy as np
import matplotlib.pyplot as plt

class InstamaticGUI(Toplevel):

    """Dialog that provide interface to map holes at high mag"""

    def __init__(self, ctrl, parent, title="Instamatic GUI"):
        Toplevel.__init__(self, parent)
        self.transient(parent)

        if title:
            self.title(title)

        self.parent = parent
        self.ctrl = ctrl
        self.drc = "."

        self.init_vars()

        body = Frame(self, padding=(10, 10, 10, 10))
        self.initial_focus = self.body(body)
        body.columnconfigure(0, weight=1)
        body.pack(fill=BOTH, anchor=CENTER, expand=True)

        self.buttonbox()
        self.update()

        # self.grab_set()

        if not self.initial_focus:
            self.initial_focus = self

        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.geometry("+%d+%d" % (parent.winfo_rootx()+50,
                                  parent.winfo_rooty()+50))

        self.initial_focus.focus_set()

        self.wait_window(self)

    def init_vars(self):
        self.var_has_stage_lowmag = BooleanVar()
        self.var_has_stage_mag1 = BooleanVar()
        self.var_has_beamshift = BooleanVar()
        self.var_has_directbeam = BooleanVar()
        
        self.msg_has_stage_lowmag = StringVar()
        self.msg_has_stage_mag1 = StringVar()
        self.msg_has_beamshift = StringVar()
        self.msg_has_directbeam = StringVar()
        
        self.var_has_holes = BooleanVar()
        self.var_has_radius = BooleanVar()
        self.var_has_params = BooleanVar()
        self.var_ready = BooleanVar()
        
        self.msg_has_holes = StringVar()
        self.msg_has_radius = StringVar()
        self.msg_has_params = StringVar()
        self.msg_ready = StringVar()

    def body(self, master):
        lf_calibration = Labelframe(master, text="Calibration", padding=(10, 10, 10, 10))
        lf_calibration.grid(row=10, sticky=E+W, columnspan=4)
        lf_calibration.grid_columnconfigure(2, weight=1)
        
        lf_experimental = Labelframe(master, text="Experimental", padding=(10, 10, 10, 10))
        lf_experimental.grid(row=20, sticky=E+W, columnspan=4)
        lf_experimental.grid_columnconfigure(2, weight=1)

        c1 = Checkbutton(lf_calibration, text="", variable=self.var_has_stage_lowmag, command=None)
        c2 = Checkbutton(lf_calibration, text="", variable=self.var_has_stage_mag1)
        c3 = Checkbutton(lf_calibration, text="", variable=self.var_has_beamshift)
        c4 = Checkbutton(lf_calibration, text="", variable=self.var_has_directbeam)
        
        c1.grid(row=1, column=0, sticky=W)
        c2.grid(row=2, column=0, sticky=W)
        c3.grid(row=3, column=0, sticky=W)
        c4.grid(row=4, column=0, sticky=W)

        Label(lf_calibration, width=20, text="Stage (lowmag)").grid(row=1, column=1, sticky=W)
        Label(lf_calibration, width=20, text="Stage (mag1)").grid(row=2, column=1, sticky=W)
        Label(lf_calibration, width=20, text="BeamShift").grid(row=3, column=1, sticky=W)
        Label(lf_calibration, width=20, text="DirectBeam").grid(row=4, column=1, sticky=W)

        e1 = Entry(lf_calibration, textvariable=self.msg_has_stage_lowmag, width=50, state="readonly")
        e2 = Entry(lf_calibration, textvariable=self.msg_has_stage_mag1, width=50, state="readonly")
        e3 = Entry(lf_calibration, textvariable=self.msg_has_beamshift, width=50, state="readonly")
        e4 = Entry(lf_calibration, textvariable=self.msg_has_directbeam, width=50, state="readonly")
        
        e1.grid(row=1, column=2, sticky=E+W, pady=2)
        e2.grid(row=2, column=2, sticky=E+W, pady=2)
        e3.grid(row=3, column=2, sticky=E+W, pady=2)
        e4.grid(row=4, column=2, sticky=E+W, pady=2)

        but1 = Button(lf_calibration, text="Run", width=10, command=self.run_stage_lowmag)
        but2 = Button(lf_calibration, text="Run", width=10, command=self.run_stage_mag1)
        but3 = Button(lf_calibration, text="Run", width=10, command=self.run_beamshift)
        but4 = Button(lf_calibration, text="Run", width=10, command=self.run_directbeam)

        but1.grid(row=1, column=3, sticky=W)
        but2.grid(row=2, column=3, sticky=W)
        but3.grid(row=3, column=3, sticky=W)
        but4.grid(row=4, column=3, sticky=W)

        c1 = Checkbutton(lf_experimental, text="", variable=self.var_has_holes)
        c2 = Checkbutton(lf_experimental, text="", variable=self.var_has_radius)
        c3 = Checkbutton(lf_experimental, text="", variable=self.var_has_params)
        c4 = Checkbutton(lf_experimental, text="", variable=self.var_ready)
        
        c1.grid(row=1, column=0, sticky=W)
        c2.grid(row=2, column=0, sticky=W)
        c3.grid(row=3, column=0, sticky=W)
        c4.grid(row=4, column=0, sticky=W)

        Label(lf_experimental, width=20, text="Holes").grid(row=1, column=1, sticky=W)
        Label(lf_experimental, width=20, text="Radius").grid(row=2, column=1, sticky=W)
        Label(lf_experimental, width=20, text="Params").grid(row=3, column=1, sticky=W)
        Label(lf_experimental, width=20, text="Ready").grid(row=4, column=1, sticky=W)

        e1 = Entry(lf_experimental, textvariable=self.msg_has_holes, width=50, state="readonly")
        e2 = Entry(lf_experimental, textvariable=self.msg_has_radius, width=50, state="readonly")
        e3 = Entry(lf_experimental, textvariable=self.msg_has_params, width=50, state="readonly")
        e4 = Entry(lf_experimental, textvariable=self.msg_ready, width=50, state="readonly")
        
        e1.grid(row=1, column=2, sticky=E+W, pady=2)
        e2.grid(row=2, column=2, sticky=E+W, pady=2)
        e3.grid(row=3, column=2, sticky=E+W, pady=2)
        e4.grid(row=4, column=2, sticky=E+W, pady=2)

        but1 = Button(lf_experimental, text="Run", width=10, command=self.run_holes)
        but2 = Button(lf_experimental, text="Run", width=10, command=self.run_radius)
        # but3 = Button(lf_experimental, text="Run", width=10, command=self.run_params)
        # but4 = Button(lf_experimental, text="Start", width=10, command=self.run_ready)

        but1.grid(row=1, column=3, sticky=W)
        but2.grid(row=2, column=3, sticky=W)
        but3.grid(row=3, column=3, sticky=W)
        # but4.grid(row=4, column=3, sticky=W)

    def buttonbox(self):
        # add standard button box. override if you don't want the
        # standard buttons

        box = Frame(self)

        self.startbutton = Button(box, text="Start", width=10, command=self.ok, state=DISABLED)
        self.startbutton.pack(side=RIGHT, padx=5, pady=5, fill=BOTH)
        w = Button(box, text="Cancel", width=10, command=self.cancel, default=ACTIVE)
        w.pack(side=RIGHT, padx=5, pady=5, fill=BOTH)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack(fill=X, anchor=S, expand=False)

    def ok(self, event=None):
        if not self.validate():
            self.initial_focus.focus_set()  # put focus back
            return

        # self.withdraw()
        self.update_idletasks()

        self.apply()

        self.cancel()

    def cancel(self, event=None):
        # put focus back to the parent window
        self.parent.focus_set()
        self.destroy()

    def default(self, event=None):
        self.set_vars()

    def validate(self):
        return 1  # override

    def apply(self):
        # run experiment
        return True

    def update(self):
        from instamatic.app import get_status
        status = get_status()
        
        self.var_has_stage_lowmag.set( status["stage_lowmag"]["ok"] )
        self.var_has_stage_mag1.set( status["stage_mag1"]["ok"] )
        self.var_has_beamshift.set( status["beamshift"]["ok"] )
        self.var_has_directbeam.set( status["directbeam"]["ok"] )
        self.msg_has_stage_lowmag.set( status["stage_lowmag"]["msg"] )
        self.msg_has_stage_mag1.set( status["stage_mag1"]["msg"] )
        self.msg_has_beamshift.set( status["beamshift"]["msg"] )
        self.msg_has_directbeam.set( status["directbeam"]["msg"] )
        self.var_has_holes.set( status["holes"]["ok"] )
        self.var_has_radius.set( status["radius"]["ok"] )
        self.var_has_params.set( status["params"]["ok"] )
        self.var_ready.set( status["ready"]["ok"] )
        self.msg_has_holes.set( status["holes"]["msg"] )
        self.msg_has_radius.set( status["radius"]["msg"] )
        self.msg_has_params.set( status["params"]["msg"] )
        self.msg_ready.set( status["ready"]["msg"] )

        if status["ready"]["ok"]:
            self.startbutton.config(state=NORMAL)

    def run_stage_lowmag(self):
        from instamatic.calibrate_stage_lowmag import calibrate_stage_lowmag
        plt.ion() # necessary to prevent blocking of stdout after plot

        okay = tkMessageBox.askokcancel("Calibrate lowmag", "Go to 100x mag, and move the sample stage so that the grid center (clover) is in the middle of the image, press OK to continue", icon='warning')
        if okay:
            calib = calibrate_stage_lowmag(ctrl=self.ctrl, confirm=False)
        print "done"

    def run_stage_mag1(self):
        from instamatic.calibrate_stage_mag1 import calibrate_stage_mag1
        plt.ion() # necessary to prevent blocking of stdout after plot

        okay = tkMessageBox.askokcancel("Calibrate beamshift", "Go to 5000x mag, and move the sample stage so that a strong feature is clearly in the middle of the image, press OK to continue", icon='warning')
        if okay:
            calib = calibrate_stage_mag1(ctrl=self.ctrl, confirm=False)
        print "done"

    def run_beamshift(self):
        from instamatic.calibrate_beamshift import calibrate_beamshift
        plt.ion() # necessary to prevent blocking of stdout after plot

        okay = tkMessageBox.askokcancel("Calibrate beamshift", "Go to 2500x mag, and move the beam by beamshift so that is in the middle of the image (use reasonable size), press OK to continue", icon='warning')
        if okay:
            calib = calibrate_beamshift(ctrl=self.ctrl, confirm=False)
        print "done"

    def run_directbeam(self):
        from instamatic.calibrate_directbeam import calibrate_directbeam
        plt.ion() # necessary to prevent blocking of stdout after plot

        okay = tkMessageBox.askokcancel("Calibrate directbeam", "Go to diffraction mode (150x) so that the beam is focused and in the middle of the image, press OK to continue", icon='warning')
        if okay:
            calib = calibrate_directbeam(ctrl=self.ctrl, confirm=False)
        print "done"

    def run_holes(self):
        from instamatic.app import map_holes_on_grid

        fns = askopenfilenames(initialdir='.', title="Select lowmag images")
        if not fns:
            return

        map_holes_on_grid(fns, plot=False, save_images=False)
        self.goto_hole()
        print "done"

    def run_radius(self):
        from prepare_experiment import PrepareExperiment
        from instamatic.app import plot_experiment, update_experiment_with_hole_coords, plot_experiment_entry
        from instamatic.app import prepare_experiment
        from instamatic.fileio import load_hole_stage_positions
        frame = PrepareExperiment(ctrl=self.ctrl, parent=self)
        
        prepare_experiment(frame.centers, frame.radii)
        coords = load_hole_stage_positions()
        update_experiment_with_hole_coords(coords)
        plot_experiment_entry()
        print "done"

    def run_params(self):
        print " >> run_params"


def start(ctrl=None):
    root = Tk()
    if not ctrl:
        from instamatic import TEMController
        ctrl = TEMController.initialize()
    frame = InstamaticGUI(ctrl, root)
    root.withdraw()
    try:
        return frame.centers, frame.radii
    except AttributeError:
        return None


if __name__ == '__main__':
    start()
