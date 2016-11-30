#!/usr/bin/env python

from Tkinter import *
from tkFileDialog import *
from ttk import *
import os

from instamatic.app import circle_center, prepare_experiment
import numpy as np

class PrepareExperiment(Toplevel):

    """Dialog that provide interface to map holes at high mag"""

    def __init__(self, ctrl, parent, title="Map holes high mag"):

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

        self.is_hole1_set = False
        self.is_hole2_set = False
        self.is_hole3_set = False

        self.buttonbox()

        self.centers = []
        self.radii = []

        # self.grab_set()

        if not self.initial_focus:
            self.initial_focus = self

        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.geometry("+%d+%d" % (parent.winfo_rootx()+50,
                                  parent.winfo_rooty()+50))

        self.initial_focus.focus_set()

        self.wait_window(self)

    def load_default(self):
        default = cfg._default()
        self.init_vars(custom_cfg=default)

    def init_vars(self):
        self.var_n_holes = IntVar()
        self.var_radius_mean = DoubleVar()

        self.var_hole1x = DoubleVar()
        self.var_hole1y = DoubleVar()
        self.var_hole2x = DoubleVar()
        self.var_hole2y = DoubleVar()
        self.var_hole3x = DoubleVar()
        self.var_hole3y = DoubleVar()

        self.set_vars()

    def set_vars(self):
        self.var_n_holes.set(0)
        self.var_radius_mean.set(0.0)

    def body(self, master):
        lf_holemap = Labelframe(master, text="Map holes", padding=(10, 10, 10, 10))
        lf_holemap.grid(row=10, sticky=E+W, columnspan=4)
        # lf_holemap.columnconfigure(0, minsize=120)
        lf_holemap.columnconfigure(1, weight=1)
        lf_holemap.columnconfigure(3, weight=1)
        lf_holemap.columnconfigure(0, minsize=15)

        Label(lf_holemap, text="X").grid(row=5, column=1, sticky=W)
        Label(lf_holemap, text="Y").grid(row=5, column=2, sticky=W)
        
        Label(lf_holemap, text="#1 ").grid(row=10, column=0, sticky=W)
        Label(lf_holemap, text="#2 ").grid(row=20, column=0, sticky=W)
        Label(lf_holemap, text="#3 ").grid(row=30, column=0, sticky=W)

        self.e_hole1x = Entry(
            lf_holemap, textvariable=self.var_hole1x, width=15)
        self.e_hole1x.grid(row=10, column=1, sticky=E+W)
        self.e_hole1y = Entry(
            lf_holemap, textvariable=self.var_hole1y, width=15)
        self.e_hole1y.grid(row=10, column=2, sticky=E+W)      
        
        self.e_hole2x = Entry(
            lf_holemap, textvariable=self.var_hole2x, width=15)
        self.e_hole2x.grid(row=20, column=1, sticky=E+W)
        self.e_hole2y = Entry(
            lf_holemap, textvariable=self.var_hole2y, width=15)
        self.e_hole2y.grid(row=20, column=2, sticky=E+W)
        
        self.e_hole3x = Entry(
            lf_holemap, textvariable=self.var_hole3x, width=15)
        self.e_hole3x.grid(row=30, column=1, sticky=E+W)
        self.e_hole3y = Entry(
            lf_holemap, textvariable=self.var_hole3y, width=15)
        self.e_hole3y.grid(row=30, column=2, sticky=E+W)
        
        but_hole1 = Button(lf_holemap, text="Set XY", width=10, command=self.set_hole1)
        but_hole2 = Button(lf_holemap, text="Set XY", width=10, command=self.set_hole2)
        but_hole3 = Button(lf_holemap, text="Set XY", width=10, command=self.set_hole3)

        but_hole1.grid(row=10, column=3, padx=5)
        but_hole2.grid(row=20, column=3, padx=5)
        but_hole3.grid(row=30, column=3, padx=5)

        self.but_accept = Button(lf_holemap, text="Add", width=10, command=self.accept_hole, state=DISABLED)
        self.but_reject = Button(lf_holemap, text="Clear", width=10, command=self.clear_hole)

        self.but_reject.grid(row=50, column=1, padx=5)     
        self.but_accept.grid(row=50, column=2, padx=5)

        Label(master, text="Holes mapped").grid(row=100, column=0, sticky=W, pady=5)
        self.e_n_holes = Entry(master, textvariable=self.var_n_holes, width=20, state="readonly")
        self.e_n_holes.grid(row=100, column=1, sticky=E+W)
        
        Label(master, text="Radius (mean)").grid(row=101, column=0, sticky=W)
        self.e_radius_mean = Entry(master, textvariable=self.var_radius_mean, width=20, state="readonly")
        self.e_radius_mean.grid(row=101, column=1, sticky=E+W)

    def buttonbox(self):
        # add standard button box. override if you don't want the
        # standard buttons

        box = Frame(self)

        w = Button(box, text="Ok", width=10, command=self.ok, default=ACTIVE)
        w.pack(side=RIGHT, padx=5, pady=5, fill=BOTH)
        w = Button(box, text="Cancel", width=10, command=self.cancel)
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
        # prepare_experiment(self.centers, self.radii)
        return True

    def update_frame(self):
        if all((self.is_hole1_set, self.is_hole2_set, self.is_hole3_set)):
            self.but_accept.configure(state=ACTIVE)

    def set_hole1(self):
        x,y,_,_,_ = self.ctrl.stageposition.get()
        # d = {"x": -10.0 , "y":10.0}
        self.var_hole1x.set( x )
        self.var_hole1y.set( y )
        self.is_hole1_set = True
        self.update_frame()

    def set_hole2(self):
        x,y,_,_,_ = self.ctrl.stageposition.get()
        # d = {"x": -10.0 , "y":10.0}
        self.var_hole2x.set( x )
        self.var_hole2y.set( y )
        self.is_hole2_set = True
        self.update_frame()

    def set_hole3(self):
        x,y,_,_,_ = self.ctrl.stageposition.get()
        # d = {"x": -10.0 , "y":10.0}
        self.var_hole3x.set( x )
        self.var_hole3y.set( y )
        self.is_hole3_set = True
        self.update_frame()

    def accept_hole(self):
        v1 = np.array((self.var_hole1x.get(), self.var_hole1y.get()))
        v2 = np.array((self.var_hole2x.get(), self.var_hole2y.get()))
        v3 = np.array((self.var_hole3x.get(), self.var_hole3y.get()))
        # v1, v2, v3 = fake_circle()
        self.clear_hole()
        self.but_accept.configure(state=DISABLED)

        try:
            center = circle_center(v1, v2, v3)
            radius = np.mean([np.linalg.norm(v - center) for v in (v1, v2, v3)])
        except:
            print " >> Could not determine circle center/radius... Try again..."
            return

        if np.any(np.isnan(center)) or np.isnan(radius):
            print " >> Could not determine circle center/radius... Try again..."
            return

        self.centers.append(center)
        self.radii.append(radius)

        print "Center:", center
        print "Radius:", radius

        self.var_radius_mean.set(np.mean(self.radii))
        self.var_n_holes.set(len(self.centers))

    def clear_hole(self):
        self.var_hole1x.set( 0.0 )
        self.var_hole1y.set( 0.0 )
        self.var_hole2x.set( 0.0 )
        self.var_hole2y.set( 0.0 )
        self.var_hole3x.set( 0.0 )
        self.var_hole3y.set( 0.0 )
        self.is_hole1_set = False
        self.is_hole2_set = False
        self.is_hole3_set = False
        self.but_accept.configure(state=DISABLED)


def start(ctrl):
    root = Tk()
    root.update()
    frame = PrepareExperiment(ctrl, root)
    return frame.centers, frame.radii


if __name__ == '__main__':
    import sys
    try:
        fname = sys.argv[1]
    except IndexError:
        fname = ""

    root = Tk()
    root.update()

    from instamatic import TEMController

    ctrl = TEMController.initialize()

    frame = PrepareExperiment(ctrl, root)
