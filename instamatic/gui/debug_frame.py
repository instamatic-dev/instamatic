from Tkinter import *
from ttk import *
import tkFileDialog
import os, sys


class DebugFrame(LabelFrame):
    """docstring for DebugFrame"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="For debugging, be careful!")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        self.e_script_file = Entry(frame, width=50, textvariable=self.script_file)
        self.e_script_file.grid(row=2, column=1, sticky="EW")

        self.BrowseButton = Button(frame, text="Browse..", command=self.browse)
        self.BrowseButton.grid(row=2, column=2, sticky="EW")
        
        self.RunButton = Button(frame, text="Run", command=self.run_script)
        self.RunButton.grid(row=2, column=3, sticky="EW")

        frame.pack(side="top", fill="x", padx=10, pady=10)

        frame = Frame(self)

        self.resetTriggers = Button(frame, text="Report status", command=self.report_status)
        self.resetTriggers.grid(row=0, column=0, sticky="EW")

        self.resetTriggers = Button(frame, text="Close down", command=self.close_down)
        self.resetTriggers.grid(row=0, column=1, sticky="EW")

        self.resetTriggers = Button(frame, text="Reset triggers", command=self.reset_triggers)
        self.resetTriggers.grid(row=1, column=0, sticky="EW")

        self.openIPython = Button(frame, text="Open IPython shell", command=self.open_ipython)
        self.openIPython.grid(row=1, column=1, sticky="EW")
        
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        frame.pack(side="bottom", fill="x", padx=10, pady=10)

    def init_vars(self):
        self.script_file = StringVar(value="script.py")

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def reset_triggers(self):
        self.triggerEvent.clear()
        print ">> trigger event has been reset."

    def open_ipython(self):
        self.q.put(("debug", { "task": "open_ipython" } ))
        self.triggerEvent.set()

    def report_status(self):
        self.q.put(("debug", { "task": "report_status" } ))
        self.triggerEvent.set()

    def close_down(self):
        self.q.put(("debug", { "task": "close_down" } ))
        self.triggerEvent.set()

    def browse(self):
        fn = tkFileDialog.askopenfilename(parent=self.parent, title="Select Python script")
        if not fn:
            return
        fn = os.path.realpath(fn)
        self.script_file.set(fn)
        return fn

    def run_script(self):
        script = self.script_file.get()
        self.q.put(("debug", { "task": "run_script", "script": script } ))
        self.triggerEvent.set()


if __name__ == '__main__':
    root = Tk()
    DebugFrame(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

