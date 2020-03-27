from tkinter import *
from tkinter.ttk import *

from instamatic import TEMController


class DefocusButton(LabelFrame):
    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='Defocus control')

        self.init_vars()

        frame = Frame(self)

        # defocus button
        Label(frame, text='Diff defocus:', width=20).grid(row=13, column=0, sticky='W')
        self.e_diff_defocus = Spinbox(frame, textvariable=self.var_diff_defocus, width=10, from_=-10000, to=10000, increment=100)
        self.e_diff_defocus.grid(row=13, column=1, sticky='EW')

        self.c_toggle_defocus = Checkbutton(frame, text='Toggle defocus', variable=self.var_toggle_diff_defocus, command=self.toggle_diff_defocus)
        self.c_toggle_defocus.grid(row=13, column=2, sticky='W', columnspan=2)

        self.b_reset_defocus = Button(frame, text='Reset', command=self.reset_diff_defocus, state=DISABLED)
        self.b_reset_defocus.grid(row=13, column=4, sticky='EW')

        frame.pack(side='top', fill='x', padx=10, pady=10)

        self.get_difffocus()

    def init_vars(self):
        self.var_diff_defocus = IntVar(value=1500)
        self.var_toggle_diff_defocus = BooleanVar(value=False)
        self.var_difffocus = IntVar(value=0)

    def get_difffocus(self, event=None):
        try:
            self.var_difffocus.set(ctrl.difffocus.get())
        except Exception:
            pass

    def toggle_diff_defocus(self):
        toggle = self.var_toggle_diff_defocus.get()

        if toggle:
            offset = self.var_diff_defocus.get()
            ctrl.difffocus.defocus(offset=offset)
            self.b_reset_defocus.config(state=NORMAL)
        else:
            ctrl.difffocus.refocus()
            self.var_toggle_diff_defocus.set(False)

        self.get_difffocus()

    def reset_diff_defocus(self):
        self.ctrl.difffocus.refocus()
        self.var_toggle_diff_defocus.set(False)
        self.get_difffocus()


def main():
    import argparse
    description = """Tiny button to focus and defocus the diffraction pattern."""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    options = parser.parse_args()

    ctrl = TEMController.initialize()

    root = Tk()
    DefocusButton(root).pack(side='top', fill='both', expand=True, padx=10, pady=10)
    root.lift()

    # keep window in front of other windows
    root.attributes('-topmost', True)

    root.title(f'Instamatic defocus helper')
    root.mainloop()


if __name__ == '__main__':
    main()
