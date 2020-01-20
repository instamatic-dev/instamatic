import tkinter.filedialog
from pathlib import Path
from tkinter import *
from tkinter.ttk import *

import matplotlib.pyplot as plt
import numpy as np

from .base_module import BaseModule
from .mpl_frame import ShowMatplotlibFig
from instamatic.formats import read_image


def treeview_sort_column(tv, col, reverse):
    """https://stackoverflow.com/a/22032582."""
    lst = [(tv.set(k, col), k) for k in tv.get_children('')]
    lst.sort(key=lambda t: float(t[0]), reverse=reverse)

    for index, (val, k) in enumerate(lst):
        tv.move(k, '', index)

    tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))


class MachineLearningFrame(LabelFrame):
    """GUI Panel to read in the results from the machine learning algorithm to
    identify good/poor crystals based on their diffraction pattern."""

    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='Neural Network')
        self.parent = parent

        self.init_vars()

        frame = Frame(self)
        columns = ('frame', 'number', 'prediction', 'size', 'x', 'y')
        self.tv = tv = Treeview(frame, columns=columns, show='headings')

        # for loop does not work here for some reason...
        tv.heading('frame', text='Frame', command=lambda: treeview_sort_column(tv, 'frame', False))
        tv.column('frame', anchor='center', width=15)
        tv.heading('number', text='Number', command=lambda: treeview_sort_column(tv, 'number', False))
        tv.column('number', anchor='center', width=15)
        tv.heading('prediction', text='Prediction', command=lambda: treeview_sort_column(tv, 'prediction', False))
        tv.column('prediction', anchor='center', width=15)
        tv.heading('size', text='Size', command=lambda: treeview_sort_column(tv, 'size', False))
        tv.column('size', anchor='center', width=15)
        tv.heading('x', text='X', command=lambda: treeview_sort_column(tv, 'x', False))
        tv.column('x', anchor='center', width=15)
        tv.heading('y', text='Y', command=lambda: treeview_sort_column(tv, 'y', False))
        tv.column('y', anchor='center', width=15)

        tv.grid(sticky=(N, S, W, E))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.pack(side='top', fill='both', expand=True, padx=10, pady=10)

        frame = Frame(self)

        self.BrowseButton = Button(frame, text='Load data', command=self.load_table)
        self.BrowseButton.grid(row=1, column=0, sticky='EW')

        self.ShowButton = Button(frame, text='Show image', command=self.show_image)
        self.ShowButton.grid(row=1, column=1, sticky='EW')

        self.GoButton = Button(frame, text='Go to crystal', command=self.go_to_crystal)
        self.GoButton.grid(row=1, column=2, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.pack(side='bottom', fill='x', padx=10, pady=10)

    def init_vars(self):
        self.fns = {}
        self.var_directory = StringVar(value=Path.cwd())

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def load_table(self):
        fn = tkinter.filedialog.askopenfilename(parent=self.parent, initialdir=self.var_directory.get(), title='Select crystal data')
        if not fn:
            return
        fn = Path(fn).resolve()

        import csv

        with open(fn, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                fn_patt, frame, number, prediction, size, stage_x, stage_y = row
                self.tv.insert('', 'end', text=fn_patt, values=(frame, number, prediction, size, stage_x, stage_y))
                self.fns[(int(frame), int(number))] = fn

        print(f'CSV data `{fn}` loaded')

    def go_to_crystal(self):
        row = self.tv.item(self.tv.focus())
        try:
            frame, number, prediction, size, stage_x, stage_y = row['values']
        except ValueError:  # no row selected
            print('No row selected')
            return

        self.q.put(('ctrl', {'task': 'stage.set',
                             'x': float(stage_x),
                             'y': float(stage_y)}))
        self.triggerEvent.set()

    def show_image(self):
        row = self.tv.item(self.tv.focus())
        try:
            frame, number, prediction, size, stage_x, stage_y = row['values']
        except ValueError:  # no row selected
            print('No row selected')
            return

        fn = Path(row['text'])

        root = fn.parents[1]
        name = fn.stem.rsplit('_', 1)[0]  # strip crystal number
        image_fn = root / 'images' / f'{name}{fn.suffix}'

        if not fn.exists():
            print(f'No such file: {fn}')
            return

        if not image_fn.exists():
            print(f'No such file: {image_fn}')
            return

        data, data_h = read_image(fn)
        img, img_h = read_image(image_fn)

        cryst_x, cryst_y = img_h['exp_crystal_coords'][number]

        fig = plt.figure()
        ax1 = plt.subplot(121, title=f'Image\nframe={frame} | number={number}\nsize={size} | x,y=({stage_x}, {stage_y})', aspect='equal')
        ax2 = plt.subplot(122, title=f'Diffraction pattern\nprediction={prediction}', aspect='equal')

        # img = np.rot90(img, k=3)                            # img needs to be rotated to match display
        cryst_y, cryst_x = img.shape[0] - cryst_x, cryst_y  # rotate coordinates

        coords = img_h['exp_crystal_coords']
        for c_x, c_y in coords:
            c_y, c_x = img.shape[0] - c_x, c_y
            ax1.plot(c_y, c_x, marker='+', color='blue', mew=2)

        ax1.imshow(img, vmax=np.percentile(img, 99.5))
        ax1.plot(cryst_y, cryst_x, marker='+', color='red', mew=2)

        ax2.imshow(data, vmax=np.percentile(data, 99.5))

        ShowMatplotlibFig(self, fig, title=fn)


module = BaseModule(name='learning', display_name='learning', tk_frame=MachineLearningFrame, location='bottom')
commands = {}


if __name__ == '__main__':
    root = Tk()
    MachineLearningFrame(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
