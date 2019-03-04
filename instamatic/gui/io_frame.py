from tkinter import *
from tkinter.ttk import *
import tkinter.filedialog
import os, sys
import datetime
from instamatic import config
from instamatic.utils.spinbox import Spinbox
from pathlib import Path


class IOFrame(LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent, basedrc=""):
        LabelFrame.__init__(self, parent, text="Input/Output")
        self.parent = parent
        
        if not basedrc:
            basedrc = config.cfg.data_directory
        else:
            basedrc = "C:/instamatic"

        self.basedrc = Path(basedrc)

        self.init_vars()

        frame = Frame(self)

        self.directory = Entry(frame, width=50, textvariable=self.var_directory)
        self.directory.grid(row=2, column=1, sticky="EW")

        self.BrowseButton = Button(frame, text="Browse..", command=self.browse_directory)
        self.BrowseButton.grid(row=2, column=2, sticky="EW")
        
        self.sample_name = Entry(frame, width=50, textvariable=self.var_sample_name)
        self.sample_name.grid(row=3, column=1, sticky="EW")

        self.flatfield = Entry(frame, width=50, textvariable=self.var_flatfield)
        self.flatfield.grid(row=4, column=1, sticky="EW")

        self.BrowseFFButton = Button(frame, text="Browse..", command=self.browse_flatfield)
        self.BrowseFFButton.grid(row=4, column=2, sticky="EW")
        
        Label(frame, text="Directory:").grid(row=2, column=0, sticky="W")
        Label(frame, text="Sample name:").grid(row=3, column=0, sticky="W")
        Label(frame, text="Flatfield:").grid(row=4, column=0, sticky="W")

        self.incrementer = Spinbox(frame, width=10, from_=0, to=999, increment=1, textvariable=self.var_experiment_number)
        self.incrementer.grid(row=3, column=2)

        frame.grid_columnconfigure(1, weight=1)

        frame.pack(side="top", fill="x", padx=10)

        frame = Frame(self)        
        self.OpenDatadirButton = Button(frame, text="Open work directory", command=self.open_data_directory)
        self.OpenDatadirButton.grid(row=1, column=0, sticky="EW")

        self.OpenConfigdirButton = Button(frame, text="Open settings directory", command=self.open_config_directory)
        self.OpenConfigdirButton.grid(row=1, column=1, sticky="EW")

        self.DeleteButton = Button(frame, text="Delete last experiment", command=self.delete_last)
        self.DeleteButton.grid(row=1, column=2, sticky="EW")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.pack(side="bottom", fill="both", padx=10, pady=10)

        self.update_experiment_number()

    def init_vars(self):
        basedrc = self.basedrc
        subdrc = "work_{}".format(datetime.datetime.now().strftime("%Y-%m-%d"))
        drc = basedrc / subdrc

        ff = config.cfg.flatfield
        if not ff:
            self.var_flatfield = StringVar(value="")
        else:
            self.var_flatfield = StringVar(value=Path(ff).absolute())

        self.var_directory = StringVar(value=drc.absolute())
        self.var_sample_name = StringVar(value="experiment")
        self.var_experiment_number = IntVar(value=1)

    def get_working_directory(self):
        drc = self.var_directory.get()
        return Path(drc)

    def update_experiment_number(self):
        drc = Path(self.var_directory.get())
        name = self.var_sample_name.get()
        number = self.var_experiment_number.get()
        path = drc / f"{name}_{number}"
        while path.exists():
            number += 1
            path = drc / f"{name}_{number}"
        self.var_experiment_number.set(number)
        return number

    def get_new_experiment_directory(self):
        number = self.update_experiment_number()
        return self.get_experiment_directory()

    def get_experiment_directory(self):
        drc = Path(self.var_directory.get())
        name = self.var_sample_name.get()
        number = self.var_experiment_number.get()
        path = drc / f"{name}_{number}"
        return path

    def browse_directory(self):
        drc = tkinter.filedialog.askdirectory(parent=self.parent, title="Select working directory")
        if not drc:
            return
        drc = Path(drc).absolute()
        self.var_directory.set(drc)
        print(self.get_experiment_directory())
        self.update_experiment_number()       # TODO: set to 1 on experiment update
        return drc

    def browse_flatfield(self):
        ff = tkinter.filedialog.askopenfilename(parent=self.parent, initialdir=self.var_directory.get(), title="Select flatfield")
        if not ff:
            return
        ff = Path(ff).absolute()
        self.var_flatfield.set(ff)
        return ff

    def get_flatfield(self):
        ff = self.var_flatfield.get()
        if ff == "":
            ff = None
        return ff

    def delete_last(self):
        drc = self.get_experiment_directory()
        date = datetime.datetime.now().strftime("%H%M%S")
        newdrc = drc.parent / f"delete_me-{date}"
        if drc.exists():
            drc.rename(newdrc)
            print(f"Marked {drc} for deletion")
        else:
            print(f"{drc} does not exist")

    def open_data_directory(self):
        drc = self.get_working_directory()
        try:
            os.startfile(drc)
        except FileNotFoundError:
            os.startfile(drc.parent)

    def open_config_directory(self):
        drc = config.base_drc
        os.startfile(drc)


from .base_module import BaseModule
module = BaseModule("io", "i/o", False, IOFrame, {})


if __name__ == '__main__':
    root = Tk()
    IOFrame(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

