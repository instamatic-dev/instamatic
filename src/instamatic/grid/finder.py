from __future__ import annotations

import argparse
from math import sqrt
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Optional

import numpy as np
import yaml

from instamatic._typing import AnyPath, float_nm, int_nm
from instamatic.grid import Intercepts
from instamatic.grid.grid import GRID_REGISTRY, PeriodicConvexPolygonGrid

if TYPE_CHECKING:
    from instamatic.gui.click_dispatcher import ClickListener


class GridFinder:
    """Base strategy for determining and updating grid geometry.
    Can be written to or read from a yaml file in the following format:

    grid_type: square
    geometry:
        x: 11111
        y: 22222  # nm
        t: 0.033  # degrees
        w: 44444
        s: 6666
    intercepts:
        0:
          - [1001, 2002]
          - [3003, 4004]
          # ...
        -1: # negative number = fresh entry, not assigned to a window yet
          - [88005, 88006]
          - [99007, 99008]
          # ...
        # ...
    """

    GRID_REGISTRY_INV = {v: k for k, v in GRID_REGISTRY.items()}

    def __init__(
        self,
        grid: Optional[PeriodicConvexPolygonGrid] = None,
        intercepts: Optional[Intercepts] = None,
    ) -> None:
        self.grid = grid or GRID_REGISTRY['square'](0, 0, 0, 85_000)
        self.intercepts: Intercepts = intercepts or {}
        self.path: Optional[AnyPath] = None  # if present, auto-save here

    @classmethod
    def from_yaml(cls, yaml_path: AnyPath) -> GridFinder:
        with open(Path(yaml_path), 'r') as f:
            data = yaml.safe_load(f)
        grid = GRID_REGISTRY[data['grid_type']](**data['geometry'])
        intercepts = data.get('intercepts', {})
        return cls(grid, {k: np.array(v, dtype=float) for k, v in intercepts.items()})

    def to_yaml(self, yaml_path: AnyPath) -> None:
        grid_type_name = self.GRID_REGISTRY_INV[type(self.grid)]
        data = {
            'grid_type': grid_type_name,
            'geometry': self.grid.to_params(),
            'intercepts': {k: v.tolist() for k, v in self.intercepts.items()},
        }
        with open(yaml_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=None, sort_keys=False)

    def add_intercept(self, window_idx: int, x: float_nm, y: float_nm) -> None:
        """Register a new intercept of given id, x, and y in the finder."""
        if window_idx in self.intercepts:
            self.intercepts[window_idx] = np.vstack([self.intercepts[window_idx], [x, y]])
        else:
            self.intercepts[window_idx] = np.array([[x, y]], dtype=float)
        if self.path is not None:
            self.to_yaml(self.path)

    def fit_intercepts(self, window_idx: int) -> None:
        """Fit all intercepts with given window id to a new window."""
        xy = self.intercepts[window_idx]
        if 0 in self.intercepts:
            new_center = (np.max(xy, axis=0) + np.min(xy, axis=0)) / 2
            new_window_idx = self.grid.nearest_index(*new_center)
        else:
            new_window_idx = 0
            self.grid = type(self.grid).guess({0: xy})
        new_intercepts = self.intercepts[window_idx]
        del self.intercepts[window_idx]
        if new_window_idx in self.intercepts:
            oi = self.intercepts[window_idx]
            self.intercepts[new_window_idx] = np.vstack([oi, new_intercepts])
        else:
            self.intercepts[new_window_idx] = new_intercepts
        self.grid.refine(self.intercepts)
        if self.path is not None:
            self.to_yaml(self.path)

    def refine_by_manual_clicking(self, ctrl, cl: ClickListener) -> None:
        """Update grid & intercepts via clicks when stage is at window edge.

        Navigate the stage to as many points on one windows edge as
        possible (at least the corners and midpoints). At each point,
        position the edge at the center of the screen and LMB to add the
        point. RMB to finish.
        """
        from instamatic.gui.click_dispatcher import MouseButton

        print(dedent(self.refine_by_manual_clicking.__doc__))
        while True:
            prev_grid, prev_intercepts = self.grid, self.intercepts
            with cl:
                while True:
                    c = cl.get_click()
                    if c.button == MouseButton.RIGHT:
                        break
                    self.add_intercept(-1, *ctrl.stage.xy)

            self.fit_intercepts(-1)
            print('Intercepts fit: LMB to accept, RMB to retry, MMB for new window')
            c = cl.get_click()
            if c.button == MouseButton.LEFT:
                break
            elif c.button == MouseButton.RIGHT:
                self.grid, self.intercepts = prev_grid, prev_intercepts
                if self.path is not None:
                    self.to_yaml(self.path)

    def refine_by_auto_sweeping(
        self,
        ctrl,
        window_idx: int = -1,
        x_lim: Optional[int_nm] = None,
        y_lim: Optional[int_nm] = None,
        arms: int = 3,
        order: Optional[int] = None,
        offset: Optional[float] = None,
    ) -> None:
        """Let grid & intercepts refine by automatically looking for edges.

        Move to `window_idx` or next window (if any present, else start here).
        If the requested window is predicted to lie inside a bounding box span
        by `x_lim` and `y_lim`, look for the edges by monitoring total beam
        intensity. `arms`, `order`, `offset` determine `star_sweep` precision.
        """
        from instamatic.grid.sweeping import star_sweep

        idx = window_idx
        if not self.intercepts:
            idx = 0
        else:
            d_lim = (sqrt(abs(max(self.intercepts))) + 2) * (self.grid.w + self.grid.h)
            x_lim = x_lim or d_lim  # crude estimate of new window search area
            y_lim = y_lim or d_lim  # if no limits was given: (sqrt(idx)+2)(w+h)
            idc_in_limits = self.grid.windows_in_limits(x=x_lim, y=y_lim)
            if idx == -1:
                try:
                    idx = min([i for i in idc_in_limits if i not in self.intercepts])
                except ValueError:
                    raise IndexError('Could not locate next window within limits')
            else:
                if idx not in idc_in_limits:
                    raise IndexError(f'Requested window {idx} is not within limits')

        if idx > 0:
            ctrl.stage.set(*[int(xy) for xy in self.grid.window(idx).center])

        smart_order = 3 if idx == 0 else 2 if len(self.intercepts.keys()) < 4 else 1
        ss_order = smart_order if order is None else order
        ss_offset = offset if offset is not None else 17 * idx

        for xy in star_sweep(arms=arms, order=ss_order, offset=ss_offset):
            self.add_intercept(idx, *xy)
        self.fit_intercepts(idx)


def main():
    """CLI tool to determine grid geometry using various methods."""

    from instamatic.controller import initialize

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        '-f',
        '--file',
        type=str,
        help='A custom path to the grid.yaml file with results',
        default='grid.yaml',
    )

    subparsers = parser.add_subparsers(
        dest='method',
        required=True,
        help='Method of grid geometry determination',
    )

    _ = subparsers.add_parser('manual', help='Manual via moving stage & input')
    a = subparsers.add_parser('auto', help='Automatically via star sweeping')

    a.add_argument(
        '--idx',
        type=int,
        default=-1,
        help='Target window index to find (default: next available window)',
    )

    a.add_argument(
        '--arms',
        type=int,
        default=3,
        choices=[3, 4, 5, 6, 7],
        help='Number of directions the sweep arms will go to find edge',
    )

    a.add_argument(
        '--order',
        type=int,
        default=None,
        choices=[1, 2, 3, 4, 5],
        help='For each order above 1, sweep also in previous orders midpoints',
    )

    a.add_argument(
        '--offset',
        type=float,
        default=None,
        help='Rotate the arms by this many degrees before first order search',
    )

    args = parser.parse_args()

    # Initialize finding logic and controller
    try:
        gf = GridFinder.from_yaml(args.file)
    except FileNotFoundError:
        gf = GridFinder()
    gf.path = args.file
    ctrl = initialize()

    if args.method == 'manual':
        # note: Daniel is an idiot. Also, for manual,
        # user needs a life view. Attach click listener there.

        from instamatic.gui.click_dispatcher import ClickEvent, MouseButton

        class TerminalClickListener:
            """Mocks ClickListener for CLI by mapping keyboard inputs to
            MouseButtons."""

            def __enter__(self) -> TerminalClickListener:
                print('Entering terminal mock for mouse button click listener.')
                print('Press "ENTER" for LMB, R+ENTER for RMB, M+ENTER for MMB.')
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

            def get_click(self) -> ClickEvent:
                """Prompt user for terminal input to simulate mouse clicks."""
                cmd = input('>> ').strip().lower()

                if cmd == 'r':
                    return ClickEvent(button=MouseButton.RIGHT)
                elif cmd == 'm':
                    return ClickEvent(button=MouseButton.MIDDLE)
                return ClickEvent(button=MouseButton.LEFT)

        cl = TerminalClickListener()
        gf.refine_by_manual_clicking(ctrl, cl)

    elif args.method == 'auto':
        gf.refine_by_auto_sweeping(
            ctrl=ctrl, window_idx=args.idx, arms=args.arms, order=args.order, offset=args.offset
        )


if __name__ == '__main__':
    main()
