from Tkinter import *
import os, sys


class IOFrame(LabelFrame):
    """docstring for ExperimentalSED"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="Input/Output")

        self.init_vars()
        
        self.root = parent

        self.directory = Entry(self, width=50, textvariable=self.var_directory)
        self.directory.grid(row=2, column=1)

        self.BrowseButton = Button(self, text="Browse..", command=self.browse_directory)
        self.BrowseButton.grid(row=2, column=2)
        
        self.sample_name = Entry(self, width=50, textvariable=self.var_sample_name)
        self.sample_name.grid(row=3, column=1)

        self.flatfield = Entry(self, width=50, textvariable=self.var_flatfield)
        self.flatfield.grid(row=4, column=1)

        self.BrowseFFButton = Button(self, text="Browse..", command=self.browse_flatfield)
        self.BrowseFFButton.grid(row=4, column=2)
        
        Label(self, width=30, text="Directory:").grid(row=2, column=0)
        Label(self, width=30, text="Sample name:").grid(row=3, column=0)
        Label(self, width=30, text="Flatfield:").grid(row=4, column=0)

        self.incrementer = Spinbox(self, from_=0, to=999, increment=1, textvariable=self.var_experiment_number)
        self.incrementer.grid(row=3, column=2)

        self.update_experiment_number()

    def init_vars(self):
        self.var_directory = StringVar(value="C:/test-gui")
        self.var_flatfield = StringVar(value="C:/test-gui/flatfield.tiff")
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

    def get_experiment_directory(self):
        self.update_experiment_number()
        drc = self.var_directory.get()
        name = self.var_sample_name.get()
        number = self.var_experiment_number.get()
        return path

    def browse_directory(self):
        import tkFileDialog
        drc = tkFileDialog.askdirectory(parent=self.root, title="Select working directory")
        self.var_directory.set(drc)
        print self.get_experiment_directory()
        self.update_experiment_number()
        return drc

    def browse_flatfield(self):
        import tkFileDialog
        ff = tkFileDialog.askopenfilename(parent=self.root, initialdir=self.var_directory.get(), title="Select flatfield")
        self.var_flatfield.set(ff)
        return ff

    def get_flatfield(self):
        return self.var_flatfield.get()


if __name__ == '__main__':
    root = Tk()
    IOFrame(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

