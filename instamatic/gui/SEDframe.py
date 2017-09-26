from Tkinter import *


class ExperimentalSED(LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Serial electron diffraction")
        self.parent = parent

        self.CollectionButton = Button(self, text="Start Collection", command=self.start_collection, anchor=W)
        self.CollectionButton.grid(row=10, column=0)

        self.CollectionStopButton = Button(self, text="Stop Collection (Does nothing)", command=self.stop_collection, anchor=W)
        self.CollectionStopButton.grid(row=11 , column=0)

        self.CalibrateBeamShiftButton = Button(self, text="Calibrate beamshift", command=None, anchor=W)
        self.CalibrateBeamShiftButton.grid(row=12 , column=0)

        self.CalibrateDirectBeamButton = Button(self, text="Calibrate direct beam", command=None, anchor=W)
        self.CalibrateDirectBeamButton.grid(row=13 , column=0)

        self.SetStartPositionButton = Button(self, text="Set", command=None, anchor=W)
        self.SetStartPositionButton.grid(row=14 , column=0)

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


if __name__ == '__main__':
    root = Tk()
    ExperimentalSED(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

