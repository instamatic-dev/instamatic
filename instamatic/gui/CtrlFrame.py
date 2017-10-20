from Tkinter import *
from ttk import *


class ExperimentalCtrl(object, LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Serial electron diffraction")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        Label(frame, text="Angle (-)", width=20).grid(row=1, column=0, sticky="W")
        Label(frame, text="Angle (0)", width=20).grid(row=2, column=0, sticky="W")
        Label(frame, text="Angle (+)", width=20).grid(row=3, column=0, sticky="W")

        Label(frame, text="Stage(X)", width=20).grid(row=5, column=0, sticky="W")
        Label(frame, text="Stage(Y)", width=20).grid(row=6, column=0, sticky="W")
        
        self.e_negative_angle   = Entry(frame, width=10, textvariable=self.var_negative_angle)
        self.e_negative_angle.grid(row=1, column=1, sticky="W")
        self.e_neutral_angle = Entry(frame, width=10, textvariable=self.var_neutral_angle)
        self.e_neutral_angle.grid(row=2, column=1, sticky="W")
        self.e_positive_angle = Entry(frame, width=10, textvariable=self.var_positive_angle)
        self.e_positive_angle.grid(row=3, column=1, sticky="W")
        self.e_stage_x = Entry(frame, width=10, textvariable=self.var_stage_x)
        self.e_stage_x.grid(row=5, column=1, sticky="W")
        self.e_stage_y = Entry(frame, width=10, textvariable=self.var_stage_y)
        self.e_stage_y.grid(row=6, column=1, sticky="W")

        Separator(frame, orient=HORIZONTAL).grid(row=4, columnspan=3, sticky="ew", pady=10)

        b_negative_angle = Button(frame, text="Set", command=self.set_negative_angle)
        b_negative_angle.grid(row=1, column=2, sticky="W")
        b_neutral_angle = Button(frame, text="Set", command=self.set_neutral_angle)
        b_neutral_angle.grid(row=2, column=2, sticky="W")
        b_positive_angle = Button(frame, text="Set", command=self.set_positive_angle)
        b_positive_angle.grid(row=3, column=2, sticky="W")
        b_stage = Button(frame, text="Set", command=self.set_stage)
        b_stage.grid(row=6, column=2, sticky="W")

        # frame.grid_columnconfigure(1, weight=1)

        frame.pack(side="top", fill="x", padx=10, pady=10)

    def init_vars(self):
        self.var_negative_angle = DoubleVar(value=-40)
        self.var_neutral_angle = DoubleVar(value=0)
        self.var_positive_angle = DoubleVar(value=40)

        self.var_stage_x = DoubleVar(value=0)
        self.var_stage_y = DoubleVar(value=0)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def set_negative_angle(self):
        self.q.put(("ctrl", { "task": "stageposition", 
                              "a": self.var_negative_angle.get() } ))
        self.triggerEvent.set()

    def set_neutral_angle(self):
        self.q.put(("ctrl", { "task": "stageposition", 
                              "a": self.var_neutral_angle.get() } ))
        self.triggerEvent.set()

    def set_positive_angle(self):
        self.q.put(("ctrl", { "task": "stageposition", 
                              "a": self.var_positive_angle.get() } ))
        self.triggerEvent.set()

    def set_stage(self):
        self.q.put(("ctrl", { "task": "stageposition", 
                              "x": self.var_stage_x.get(),
                              "y": self.var_stage_y.get() } ))
        self.triggerEvent.set()


if __name__ == '__main__':
    root = Tk()
    ExperimentalCTRL(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

