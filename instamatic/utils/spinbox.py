from tkinter.ttk import Entry

# https://github.com/alandmoore/cpython/blob/53046dcf91481f3e69ddbc97e5d8d0d921c1d09f/Lib/tkinter/ttk.py


class Spinbox(Entry):
    """Ttk Spinbox is an Entry with increment and decrement arrows It is
    commonly used for number entry or to select from a list of string
    values."""

    def __init__(self, master=None, **kw):
        """Construct a Ttk Spinbox widget with the parent master.

        STANDARD OPTIONS: class, cursor, style, takefocus, validate,
        validatecommand, xscrollcommand, invalidcommand

        WIDGET-SPECIFIC OPTIONS: to, from_, increment, values, wrap, format, command
        """
        Entry.__init__(self, master, 'ttk::spinbox', **kw)

    def set(self, value):
        """Sets the value of the Spinbox to value."""
        self.tk.call(self._w, 'set', value)
