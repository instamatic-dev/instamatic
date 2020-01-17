class BaseModule:
    """BaseModule for the gui composition.

    `location` must be one of 'top', 'bottom', 'left', 'right' `kwargs`
    are to be passed on to the `tk_frame` class during initialization
    """

    def __init__(self,
                 name: str,
                 tk_frame: 'tkinter.Frame',
                 display_name: str = None,
                 location: str = 'top',
                 **kwargs):
        super().__init__()

        self.name = name
        self.display_name = display_name if display_name else name
        self.tk_frame = tk_frame
        self.location = location
        self.kwargs = kwargs

    def set_kwargs(self, **kwargs):
        self.kwargs = kwargs

    def initialize(self, parent):
        frame = self.tk_frame(parent, **self.kwargs)
        self.frame = frame
        return frame
