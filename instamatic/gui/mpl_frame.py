from tkinter import *
from tkinter.ttk import *

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class ShowMatplotlibFig(Toplevel):
    """Simple class to load a matplotlib figure in a new top level panel."""

    def __init__(self, parent, fig, title='figure'):
        Toplevel.__init__(self, parent)
        self.grab_set()
        self.title(title)
        button = Button(self, text='Dismiss', command=self.close)
        button.pack(side=BOTTOM)
        self.canvas = canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.show()
        canvas.get_tk_widget().pack(side=TOP, fill=BOTH, expand=True)
        # canvas._tkcanvas.pack(side=self, fill=BOTH, expand=True)
        self.wm_protocol('WM_DELETE_WINDOW', self.close)
        self.focus_set()
        self.wait_window(self)

    def close(self, event=None):
        self.canvas.get_tk_widget().destroy()
        self.destroy()    # this is necessary on Windows to prevent
        # Fatal Python Error: PyEval_RestoreThread: NULL tstate
        plt.clf()
        plt.close('all')
