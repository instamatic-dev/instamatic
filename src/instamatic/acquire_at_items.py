from __future__ import annotations

from collections import defaultdict

import numpy as np
from tqdm.auto import tqdm


class AcquireAtItems:
    """Class to automated acquisition at many stage locations. The acquisition
    functions must be callable (or a list of callables) that accept `ctrl` as
    an argument. In case a list of callables is given, they are excecuted in
    sequence.

    Parameters
    ----------
    ctrl: Instamatic.TEMController object
        Used to control the stage and TEM
    nav_items: list
        List of (x, y) / (x, y, z) coordinates (nm), or
        List of navigation items loaded from a `.nav` file.
    acquire: callable, list of callables
        Main function to call, must take `ctrl` as an argument
    pre_acquire: callable, list of callables
        This function is called before the first acquisition item is run.
    post_acquire: callable, list of callables
        This function is run after the last acquisition item has run.
    every_n: dict
        Dictionary with functions to run every `n` positions. Each value must be
        a callable or a list of callables taking a `ctrl` object as its agument,
        e.g. every_n={2: every_2nd, 3: every_3rd}. These will be called in
        sequence _after_ the main acquisition function.
    backlash: bool
        Move the stage with backlash correction.

    Returns
    -------
    aai: `AcquireatItems`
        Returns instance of AcquireAtItems, run `aai.start()` to begin.
    """

    def __init__(
        self,
        ctrl,
        nav_items: list,
        acquire=None,
        pre_acquire=None,
        post_acquire=None,
        every_n: dict = {},
        backlash: bool = True,
    ):
        super().__init__()

        self.nav_items = nav_items
        self.ctrl = ctrl

        if pre_acquire:
            self._pre_acquire = self.validate(pre_acquire)
            print('Pre-acquire:', ', '.join([func.__name__ for func in self._pre_acquire]))

        if acquire:
            self._acquire = defaultdict(list)
            self._acquire[1].extend(self.validate(acquire))
            for interval, funcs in every_n.items():
                self._acquire[interval].extend(self.validate(funcs))

            for interval, funcs in self._acquire.items():
                print(f'Acquire[{interval}]:', ', '.join([func.__name__ for func in funcs]))

            self._acquire_intervals = np.array(list(self._acquire.keys()))

        if post_acquire:
            self._post_acquire = self.validate(post_acquire)
            print('Post-acquire:', ', '.join([func.__name__ for func in self._post_acquire]))

        self.backlash = backlash

    # blank placeholders
    _acquire = ()
    _pre_acquire = ()
    _post_acquire = ()

    def validate(self, funcs):
        """`func` can be a callable or a list of callables."""
        if not isinstance(funcs, (list, tuple)):
            funcs = (funcs,)

        for func in funcs:
            assert callable(func), f'{func} is not a function!'

        return funcs

    def pre_acquire(self, ctrl):
        """Handler to call functions the first stage position/NavItem."""
        for func in self._pre_acquire:
            func(ctrl)

    def post_acquire(self, ctrl):
        """Handler to call functions after the last stage position/NavItem."""
        for func in self._post_acquire:
            func(ctrl)

    def acquire(self, ctrl, i: int = 1):
        """Handler to call functions at each stage position/NavItem (or at
        specific intervals)."""
        r = self._acquire_intervals
        tasks = r[(i + 1) % r == 0]
        for interval in tasks:
            funcs = self._acquire[interval]
            for func in funcs:
                # print(f" >> {interval}: {func.__name__}")
                func(ctrl)

    def move_to_item(self, item):
        """Move the stage to the stage coordinates given by the NavItem."""
        try:
            x = item.stage_x * 1000  # um -> nm
            y = item.stage_y * 1000  # um -> nm
            z = item.stage_z * 1000  # um -> nm
        except AttributeError:
            if len(item) == 2:
                x, y = item
                z = None
            elif len(item) == 3:
                x, y, z = item
            else:
                raise IndexError(
                    f'Coordinate must have 2 (x, y) or 3 (x, y, z) elements: {item}'
                )

        if z is not None:
            self.ctrl.stage.set(z=z)

        if self.backlash:
            set_xy = self.ctrl.stage.set_xy_with_backlash_correction
        else:
            set_xy = self.ctrl.stage.set

        set_xy(x=x, y=y)

    def start(self, start_index: int = 0):
        """Start serial acquisition protocol.

        Parameters
        ----------
        start_index : int
            Start acquisition from this item.
        """
        import msvcrt
        import time

        ctrl = self.ctrl
        nav_items = self.nav_items[start_index:]

        ntot = len(nav_items)

        print(f'\nAcquiring on {ntot} items.')
        print('Press <Ctrl-C> or ⬛ to interrupt.\n')

        self.move_to_item(nav_items[0])  # pre-move
        self.pre_acquire(ctrl)

        t0 = time.perf_counter()

        for i, item in enumerate(tqdm(nav_items)):
            # Run script in try/except block so that Keyboard interrupt
            # will safely break out of the loop
            try:
                i += start_index
                ctrl.current_item = item
                ctrl.current_i = i

                self.move_to_item(item)
                self.acquire(ctrl, i=i)

            except (Exception, KeyboardInterrupt) as e:
                print(repr(e.with_traceback(None)))
                print(f'\nAcquisition was interrupted during item `{item}`!')
                break

        t1 = time.perf_counter()

        self.post_acquire(ctrl)

        dt = t1 - t0
        n_items = i + 1
        print(f'Total time taken: {dt:.0f} s for {n_items} items ({dt / n_items:.2f} s/item)')
        print('\nAll done!')
