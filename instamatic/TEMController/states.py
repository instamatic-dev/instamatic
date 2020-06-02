import time


class State:
    """Class for describing microscope state objects."""

    def __init__(self, tem):
        super().__init__()
        self._tem = tem
        self._getter = None
        self._setter = None

    def __repr__(self):
        return f'{self.name}({repr(self.state)})'

    def __eq__(self, other):
        """Allow `str` comparison."""
        if isinstance(other, str):
            return self.state == other
        return False

    @property
    def name(self) -> str:
        return self.__class__.__name__


class Beam(State):
    """Control for the beam blanker."""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setBeamBlank
        self._getter = self._tem.isBeamBlanked
        self._states = 'unblanked', 'blanked'

    @property
    def state(self):
        """Return the status of the beam blanker as a `str` (on/off)"""
        return self.get()

    @property
    def is_blanked(self) -> bool:
        """Return the status of the beam blanker as a `bool`"""
        return self._getter()

    def blank(self, delay: float = 0.0) -> None:
        """Turn the beamblank on, optionally wait for `delay` in ms to allow
        the beam to settle."""
        self._setter(True)
        if delay:
            time.sleep(delay)

    def unblank(self, delay: float = 0.0) -> None:
        """Turn the beamblank off, optionally wait for `delay` in ms to allow
        the beam to settle."""
        self._setter(False)
        if delay:
            time.sleep(delay)

    def set(self, state: str, delay: float = 0.0):
        index = self._states.index(state)
        f = (self.unblank, self.blank)[index]
        f(delay=delay)

    def get(self) -> str:
        return self._states[self.is_blanked]


class Mode(State):
    """Control for the magnification mode."""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setFunctionMode
        self._getter = self._tem.getFunctionMode

    @property
    def state(self) -> str:
        return self.get()

    def set(self, mode: str) -> None:
        """Set the function mode."""
        self._setter(mode)

    def get(self) -> str:
        """Returns the function mode."""
        return self._getter()


class Screen(State):
    """Control for the fluorescence screen."""

    def __init__(self, tem):
        super().__init__(tem=tem)
        self._setter = self._tem.setScreenPosition
        self._getter = self._tem.getScreenPosition
        self._DOWN = 'down'
        self._UP = 'up'

    @property
    def state(self) -> str:
        """Return the position of the screen as a `str`"""
        return self.get()

    @property
    def is_up(self) -> bool:
        """Return the position of the screen as a `bool`"""
        return self.state == self._UP

    def up(self) -> None:
        """Raise the fluorescence screen."""
        self.set(self._UP)

    def down(self) -> None:
        """Lower the fluorescence screen."""
        self.set(self._DOWN)

    def get(self) -> str:
        """Get the position of the fluorescence screen."""
        return self._getter()

    def set(self, state: str) -> None:
        """Set the position of the fluorescence screen (up/down)."""
        self._setter(state)
