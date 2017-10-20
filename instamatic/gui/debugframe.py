from Tkinter import *
from ttk import *


class DebugFrame(LabelFrame):
    """docstring for DebugFrame"""
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text="For debugging, be careful!")
        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        self.resetTriggers = Button(frame, text="Reset triggers", command=self.reset_triggers)
        self.resetTriggers.grid(row=1, column=0, sticky="EW")

        self.openIPython = Button(frame, text="Open IPython shell", command=self.open_ipython)
        self.openIPython.grid(row=1, column=1, sticky="EW")
        
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        frame.pack(side="bottom", fill="x", padx=10, pady=10)

    def init_vars(self):
        pass

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def reset_triggers(self):
        self.triggerEvent.clear()
        print ">> trigger event has been reset."

    def open_ipython(self):
        self.q.put(("debug", { "task": "open_ipython" } ))
        self.triggerEvent.set()


if __name__ == '__main__':
    root = Tk()
    DebugFrame(root).pack(side="top", fill="both", expand=True)
    root.mainloop()

