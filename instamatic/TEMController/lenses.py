class Lens:
    """Generic microscope lens object defined by one value Must be subclassed
    to set the self._getter, self._setter functions."""

    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self._getter = None
        self._setter = None
        self.key = 'lens'

    def __repr__(self):
        try:
            value = self.value
        except ValueError:
            value = 'n/a'
        return f'{self.name}(value={value})'

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def set(self, value: int):
        self._setter(value)

    def get(self) -> int:
        return self._getter()

    @property
    def value(self) -> int:
        return self.get()

    @value.setter
    def value(self, value: int):
        self.set(value)


class DiffFocus(Lens):
    """Control the Difffraction focus lens (IL1)"""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getDiffFocus
        self._setter = self._tem.setDiffFocus
        self.is_defocused = False

    def set(self, value: int, confirm_mode: bool = True):
        """
        confirm_mode: verify that TEM is set to the correct mode ('diff').
        IL1 maps to different values in image and diffraction mode.
        Turning it off results in a 2x speed-up in the call, but it will silently fail if the TEM is in the wrong mode.
        """
        self._setter(value, confirm_mode=confirm_mode)

    def defocus(self, offset):
        """Apply a defocus to the IL1 lens, use `.refocus` to restore the
        previous setting."""
        if self.is_defocused:
            raise TEMControllerError(f'{self.__class__.__name__} is already defocused!')

        try:
            self._focused_value = current = self.get()
        except ValueError:
            self._tem.setFunctionMode('diff')
            self._focused_value = current = self.get()

        target = current + offset
        self.set(target)
        self.is_defocused = True
        print(f'Defocusing from {current} to {target}')

    def refocus(self):
        """Restore the IL1 lens to the focused condition a defocus has been
        applied using `.defocus`"""
        if self.is_defocused:
            target = self._focused_value
            self.set(target)
            self.is_defocused = False
            print(f'Refocusing to {target}')


class Brightness(Lens):
    """Control object for the Brightness (CL3)"""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getBrightness
        self._setter = self._tem.setBrightness

    def max(self):
        self.set(65535)

    def min(self):
        self.set(0)


class Magnification(Lens):
    """Magnification control.

    The magnification can be set directly, or by passing the
    corresponding index
    """

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._getter = self._tem.getMagnification
        self._setter = self._tem.setMagnification
        self._indexgetter = self._tem.getMagnificationIndex
        self._indexsetter = self._tem.setMagnificationIndex

    def __repr__(self):
        value = self.value
        index = self.index
        return f'Magnification(value={value}, index={index})'

    @property
    def index(self) -> int:
        return self._indexgetter()

    @property
    def absolute_index(self) -> int:
        return self._tem.getMagnificationAbsoluteIndex()

    @index.setter
    def index(self, index: int):
        self._indexsetter(index)

    def increase(self) -> None:
        try:
            self.index += 1
        except ValueError:
            print(f'Error: Cannot change magnficication index (current={self.value}).')

    def decrease(self) -> None:
        try:
            self.index -= 1
        except ValueError:
            print(f'Error: Cannot change magnficication index (current={self.value}).')

    def get_ranges(self) -> dict:
        """Runs through all modes and fetches all the magnification settings
        possible on the microscope."""
        return self._tem.getMagnificationRanges()
