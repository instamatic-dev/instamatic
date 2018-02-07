from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from tkinter import *
from tkinter.ttk import *
import tkinter.filedialog
import os, sys
import glob
from instamatic.config import config_dir


class DebugFrame(LabelFrame):
    """docstring for DebugFrame"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="For debugging, be careful!")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        Label(frame, text="Run custom python scripts").grid(row=1, column=0, sticky="W")

        self.e_script_file = Combobox(frame, width=50, textvariable=self.script_file, values=list(self.scripts.keys()))
        self.e_script_file.grid(row=2, column=0, columnspan=2, sticky="EW")
        self.scripts_combobox_update()

        self.BrowseButton = Button(frame, text="Browse..", command=self.browse)
        self.BrowseButton.grid(row=2, column=2, sticky="EW")
        
        self.RunButton = Button(frame, text="Run", command=self.run_script)
        self.RunButton.grid(row=2, column=3, sticky="EW")
        
        Separator(frame, orient=HORIZONTAL).grid(row=3, columnspan=4, sticky="ew", pady=10)

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

        self.resetTriggers = Button(frame, text="Empty queue", command=self.empty_queue)
        self.resetTriggers.grid(row=2, column=0, sticky="EW")
        
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        frame.pack(side="bottom", fill="x", padx=10, pady=10)

    def init_vars(self):
        self.script_file = StringVar()
        self.scripts = {}
        self.scripts_dir = os.path.join(config_dir, "scripts")

    def scripts_combobox_update(self, event=None):
        for fn in glob.glob(os.path.join(self.scripts_dir, "*.py")):
            self.scripts[os.path.basename(fn)] = fn
        self.e_script_file['values'] = list(self.scripts.keys())

    def scripts_combobox_add(self, fn):
        self.scripts[os.path.basename(fn)] = fn
        self.e_script_file['values'] = list(self.scripts.keys())

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def reset_triggers(self):
        self.triggerEvent.clear()
        print(">> trigger event has been reset.")

    def empty_queue(self):
        print("There are {} items left in the queue.".format(self.q.qsize()))
        while not self.q.empty():
            job, kwargs = self.q.get()
            print("Flushed job: {}->{}".format(job, kwargs))

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
        fn = tkinter.filedialog.askopenfilename(parent=self.parent, title="Select Python script")
        if not fn:
            return
        fn = os.path.realpath(fn)
        self.scripts_combobox_add(fn)
        self.script_file.set(fn)
        return fn

    def run_script(self):
        script = self.script_file.get()
        if script in self.scripts:
            script = self.scripts[script]
        self.q.put(("debug", { "task": "run_script", "script": script } ))
        self.triggerEvent.set()


if __name__ == '__main__':
    root = Tk()
    DebugFrame(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

