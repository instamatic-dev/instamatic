# coding: future_fstrings 

from tkinter import *
from tkinter.ttk import *


class ExperimentalCtrl(LabelFrame):
    """docstring for ExperimentalCtrl"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Stage Control")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        cb_nowait = Checkbutton(frame, text="Wait for stage", variable=self.var_stage_wait)
        cb_nowait.grid(row=0, column=1)

        b_stage_stop = Button(frame, text="Stop stage", command=self.stage_stop)
        b_stage_stop.grid(row=0, column=0, sticky="W")

        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)

        Label(frame, text="Angle (-)", width=20).grid(row=1, column=0, sticky="W")
        Label(frame, text="Angle (0)", width=20).grid(row=2, column=0, sticky="W")
        Label(frame, text="Angle (+)", width=20).grid(row=3, column=0, sticky="W")

        Label(frame, text="Stage(XY)", width=20).grid(row=5, column=0, sticky="W")
        
        e_negative_angle = Entry(frame, width=10, textvariable=self.var_negative_angle)
        e_negative_angle.grid(row=1, column=1, sticky="EW")
        e_neutral_angle = Entry(frame, width=10, textvariable=self.var_neutral_angle)
        e_neutral_angle.grid(row=2, column=1, sticky="EW")
        e_positive_angle = Entry(frame, width=10, textvariable=self.var_positive_angle)
        e_positive_angle.grid(row=3, column=1, sticky="EW")
        e_stage_x = Entry(frame, width=10, textvariable=self.var_stage_x)
        e_stage_x.grid(row=5, column=1, sticky="EW")
        e_stage_y = Entry(frame, width=10, textvariable=self.var_stage_y)
        e_stage_y.grid(row=5, column=2, sticky="EW")

        b_negative_angle = Button(frame, text="Set", command=self.set_negative_angle)
        b_negative_angle.grid(row=1, column=2, sticky="W")
        b_neutral_angle = Button(frame, text="Set", command=self.set_neutral_angle)
        b_neutral_angle.grid(row=2, column=2, sticky="W")
        b_positive_angle = Button(frame, text="Set", command=self.set_positive_angle)
        b_positive_angle.grid(row=3, column=2, sticky="W")
        b_stage = Button(frame, text="Set", command=self.set_stage)
        b_stage.grid(row=5, column=3, sticky="W")

        # frame.grid_columnconfigure(1, weight=1)
        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)
        
        Label(frame, text="Brightness", width=20).grid(row=11, column=0, sticky="W")
        e_brightness = Entry(frame, width=10, textvariable=self.var_brightness)
        e_brightness.grid(row=11, column=1, sticky="W")

        b_brightness = Button(frame, text="Set", command=self.set_brightness)
        b_brightness.grid(row=11, column=2, sticky="W")

        slider = Scale(frame, variable=self.var_brightness, from_=0, to=2**16-1, orient=HORIZONTAL, command=self.set_brightness)
        slider.grid(row=12, column=0, columnspan=3, sticky="EW")

        frame.pack(side="top", fill="x", padx=10, pady=10)

    def init_vars(self):
        self.var_negative_angle = DoubleVar(value=-40)
        self.var_neutral_angle = DoubleVar(value=0)
        self.var_positive_angle = DoubleVar(value=40)

        self.var_stage_x = DoubleVar(value=0)
        self.var_stage_y = DoubleVar(value=0)
        
        self.var_brightness = IntVar(value=65535)

        self.var_stage_wait = BooleanVar(value=True)

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def set_brightness(self, event=None):
        self.var_brightness.set((self.var_brightness.get()))
        self.q.put(("ctrl", { "task": "brightness.set", 
                              "value": self.var_brightness.get() } ))
        self.triggerEvent.set()

    def set_negative_angle(self):
        self.q.put(("ctrl", { "task": "stageposition.set", 
                              "a": self.var_negative_angle.get(),
                              "wait": self.var_stage_wait.get()  } ))
        self.triggerEvent.set()

    def set_neutral_angle(self):
        self.q.put(("ctrl", { "task": "stageposition.set", 
                              "a": self.var_neutral_angle.get(),
                              "wait": self.var_stage_wait.get()  } ))
        self.triggerEvent.set()

    def set_positive_angle(self):
        self.q.put(("ctrl", { "task": "stageposition.set", 
                              "a": self.var_positive_angle.get(),
                              "wait": self.var_stage_wait.get()  } ))
        self.triggerEvent.set()

    def set_stage(self):
        self.q.put(("ctrl", { "task": "stageposition.set", 
                              "x": self.var_stage_x.get(),
                              "y": self.var_stage_y.get(),
                              "wait": self.var_stage_wait.get() } ))
        self.triggerEvent.set()

    def stage_stop(self):
        self.q.put(("ctrl", { "task": "stageposition.stop" } ))
        self.triggerEvent.set()



def microscope_control(controller, **kwargs):
    from operator import attrgetter

    task = kwargs.pop("task")

    f = attrgetter(task)(controller.ctrl)  # nested getattr
    f(**kwargs)


from .base_module import BaseModule
module = BaseModule("ctrl", "ctrl", True, ExperimentalCtrl, commands={
    "ctrl": microscope_control
    })


if __name__ == '__main__':
    root = Tk()
    ExperimentalCtrl(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

