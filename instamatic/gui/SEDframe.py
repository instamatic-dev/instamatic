from Tkinter import *
import tkMessageBox


class ExperimentalSED(LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Serial electron diffraction")
        self.parent = parent

        self.init_vars()

        # self.CalibrateBeamShiftButton = Button(self, text="Calibrate beamshift", command=self.run_beamshift_calibration, anchor=W)
        # self.CalibrateBeamShiftButton.grid(row=8 , column=0)

        # self.CalibrateDirectBeamButton = Button(self, text="Calibrate direct beam", command=self.run_directbeam_calibration, anchor=W)
        # self.CalibrateDirectBeamButton.grid(row=9 , column=0)

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

        self.CollectionButton = Button(self, text="Start Collection", command=self.start_collection, anchor=W, state=NORMAL)
        self.CollectionButton.grid(row=10, column=0)

    def init_vars(self):
        self.var_start_x = DoubleVar(value=0)
        self.var_start_y = DoubleVar(value=0)
        self.var_scan_area = DoubleVar(value=100)

    def set_trigger(self, trigger=None):
        self.triggerEvent = trigger

    def set_events(self, startEvent=None, stopEvent=None):
        self.startEvent = startEvent
        self.stopEvent = stopEvent

    def start_collection(self):
        print "Start button pressed"
        self.startEvent.set()
        self.triggerEvent.set()

    def stop_collection(self):
        print "Stop button pressed"
        self.stopEvent.set()

    def setStartPosition(self):
        x,y  = self.ctrl.xy
        self.var_start_x.set(x)
        self.var_start_y.set(y)


if __name__ == '__main__':
    root = Tk()
    ExperimentalSED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

