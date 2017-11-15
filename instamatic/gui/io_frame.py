from Tkinter import *
from ttk import *
import tkFileDialog
import os, sys
import datetime


class IOFrame(LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent, basedrc="C:/instamatic"):
        LabelFrame.__init__(self, parent, text="Input/Output")
        self.parent = parent
        self.basedrc = basedrc

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

        self.OpenDatadirButton = Button(frame, text="Open work directory", command=self.open_data_directory)
        self.OpenDatadirButton.grid(row=5, column=0, sticky="EW")

        frame.grid_columnconfigure(1, weight=1)

        frame.pack(side="top", fill="x", padx=10)

        frame = Frame(self)

        self.CollectionButton = Button(frame, text="Delete last experiment because it was awful =(", command=self.delete_last, state=NORMAL)
        self.CollectionButton.pack(side="bottom", fill="both")

        frame.pack(side="bottom", fill="both", padx=10, pady=10)

        self.update_experiment_number()

    def init_vars(self):
        basedrc = self.basedrc
        subdrc = "work_{}".format(datetime.datetime.now().strftime("%Y-%m-%d"))
        drc = os.path.join(basedrc, subdrc)
        ff_path = os.path.join(basedrc, "flatfield.tiff")

        self.var_directory = StringVar(value=os.path.realpath(drc))
        self.var_flatfield = StringVar(value=os.path.realpath(ff_path))
        self.var_sample_name = StringVar(value="experiment")
        self.var_experiment_number = IntVar(value=1)

    def get_working_directory(self):
        drc = self.var_directory.get()
        return drc

    def update_experiment_number(self):
        drc = self.var_directory.get()
        name = self.var_sample_name.get()
        number = self.var_experiment_number.get()
        path = os.path.join(drc, "{}_{}".format(name, number))
        while os.path.exists(path):
            number += 1
            path = os.path.join(drc, "{}_{}".format(name, number))
        self.var_experiment_number.set(number)
        return number

    def get_new_experiment_directory(self):
        number = self.update_experiment_number()
        return self.get_experiment_directory()

    def get_experiment_directory(self):
        drc = self.var_directory.get()
        name = self.var_sample_name.get()
        number = self.var_experiment_number.get()
        path = os.path.join(drc, "{}_{}".format(name, number))
        return path

    def browse_directory(self):
        drc = tkFileDialog.askdirectory(parent=self.parent, title="Select working directory")
        if not drc:
            return
        drc = os.path.realpath(drc)
        self.var_directory.set(drc)
        print self.get_experiment_directory()
        self.update_experiment_number()       # TODO: set to 1 on experiment update
        return drc

    def browse_flatfield(self):
        ff = tkFileDialog.askopenfilename(parent=self.parent, initialdir=self.var_directory.get(), title="Select flatfield")
        if not ff:
            return
        ff = os.path.realpath(ff)
        self.var_flatfield.set(ff)
        return ff

    def get_flatfield(self):
        return self.var_flatfield.get()

    def delete_last(self):
        drc = self.get_experiment_directory()
        newdrc = drc+"-delete_me-"+datetime.datetime.now().strftime("%H%M%S")
        if os.path.exists(drc):
            os.rename(drc, newdrc)
            print "Marked {} for deletion".format(drc)
        else:
            print "{} does not exist".format(drc)

    def open_data_directory(self):
        drc = self.get_working_directory()
        os.startfile(drc)


if __name__ == '__main__':
    root = Tk()
    IOFrame(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

