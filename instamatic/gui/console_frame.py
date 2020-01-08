import datetime
import sys
import time
from pathlib import Path
from tkinter import *
from tkinter import filedialog
from tkinter.scrolledtext import ScrolledText
from tkinter.ttk import *

from .base_module import BaseModule
from instamatic import config


class Writer:
    """Overwrite stdout with this class to write to a tkinter text widget.

    text: `tkinter.Text`
        Tkinter text / scrolledtext widget to redirect stdout to
    """

    def __init__(self, text):
        self.terminal = sys.stdout
        self.text = text
        self._timestamp = False

    def write(self, message):
        self.terminal.write(message)
        if self._timestamp and message != '\n':
            now = time.strftime('%H:%M:%S')
            self.text.insert(END, f'[{now}] {message}')
        else:
            self.text.insert(END, message)
        self.text.see(END)

    def flush(self, *args, **kwargs):
        self.terminal.flush(*args, **kwargs)

    def timestamp(self, toggle):
        self._timestamp = toggle


class Console(LabelFrame):
    """Docstring for Console."""

    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='Console')
        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        self.text = ScrolledText(frame, width=20)
        self.text.grid(sticky=(N, S, W, E))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.pack(side='top', fill='both', expand=True, padx=10, pady=10)

        frame = Frame(self)

        self.TestButton = Button(frame, text='Test', command=self.write)
        self.TestButton.grid(row=1, column=0, sticky='EW')

        self.CaptureButton = Button(frame, text='Capture', command=self.redirect_stdout)
        self.CaptureButton.grid(row=1, column=1, sticky='EW')

        self.ResetButton = Button(frame, text='Reset', command=self.reset_stdout)
        self.ResetButton.grid(row=1, column=2, sticky='EW')

        self.ClearButton = Button(frame, text='Clear', command=self.clear_text)
        self.ClearButton.grid(row=1, column=3, sticky='EW')

        self.ExportButton = Button(frame, text='Export', command=self.export_text)
        self.ExportButton.grid(row=1, column=4, sticky='EW')

        self.TimestampButton = Checkbutton(frame, text='Timestamp', variable=self.var_toggle_timestamp, command=self.toggle_timestamp)
        self.TimestampButton.grid(row=1, column=5, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.columnconfigure(4, weight=1)
        frame.columnconfigure(5, weight=1)

        frame.pack(side='top', fill='x')

        self.redirect_stdout()

    def init_vars(self):
        self.var_toggle_timestamp = BooleanVar(value=False)

    def write(self, text=None):
        """Test write a line to the console."""
        if not text:
            text = str(datetime.datetime.now())
        print(text)

    def redirect_stdout(self):
        """Redirect stdout to print also to the console."""
        self.writer = Writer(self.text)
        self.regular_stdout = sys.stdout
        sys.stdout = self.writer

    def reset_stdout(self):
        """Stop logging text and restore normal stdout."""
        sys.stdout = self.regular_stdout

    def clear_text(self, show=10):
        """Clear the text in the console."""
        self.text.delete('0.0', END)

    def export_text(self):
        """Export text from the text widget to a file."""

        drc = config.cfg.work_directory

        f = filedialog.asksaveasfile(mode='w',
                                     defaultextension='.txt',
                                     filetypes=(('Text', '*.txt'),),
                                     initialdir=drc,
                                     initialfile='console.txt')

        if not f:
            return

        text = str(self.text.get(1.0, END))  # starts from `1.0`, not `0.0`

        f.write(text)
        f.close()

        self.clear_text()

    def toggle_timestamp(self):
        """Print a timestamp at the beginning of each new line."""
        toggle = self.var_toggle_timestamp.get()
        if toggle:
            self.writer.timestamp(toggle)
        else:
            self.writer.timestamp(toggle)


module = BaseModule('console', 'console', True, Console, commands={})

if __name__ == '__main__':
    root = Tk()
    Console(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
