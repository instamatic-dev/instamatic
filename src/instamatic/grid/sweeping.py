from __future__ import annotations

from dataclasses import dataclass
from itertools import chain
from typing import Any, Generator, Literal, Optional, Sequence, Union

import numpy as np
from typing_extensions import Self

from instamatic._typing import float_deg, float_nm, int_nm
from instamatic.controller import TEMController, _ctrl, initialize
from instamatic.grid import cross2d, versor
from instamatic.utils.iterating import pairwise

if not _ctrl:
    _ctrl: TEMController = initialize()


Vector2 = Sequence[float]


class InstanceAutoNameRegistry:
    """Autosave each subclass instance in `cls.INSTANCES` dict under `name`"""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.INSTANCES: dict[Any, Self] = {}

    def __post_init__(self):
        self.__class__.INSTANCES[getattr(self, 'name')] = self


class Sweeper:
    """A simple descriptor of stage movement with fixed heading."""

    def __init__(self, origin: Vector2, heading: Vector2) -> None:
        self.origin = np.array([origin[0], origin[1]], dtype=float)
        self.heading = np.array([heading[0], heading[1]], dtype=float)
        self.position = np.array([origin[0], origin[1]], dtype=float)

    def dist2segment(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Dist to intercept a segment or +inf, stackoverflow.com/q/2931573."""
        ray1o = self.origin
        ray1h = self.heading
        ray2o = np.array([x1, y1], dtype=float)
        ray2h = np.array([x2 - x1, y2 - y1], dtype=float)
        delta = ray2o - ray1o
        cross = cross2d(ray1h, ray2h)
        if cross == 0:
            return np.inf
        ray1d = cross2d(delta, ray2h) / cross
        ray2d = cross2d(delta, ray1h) / cross
        if ray1d >= 0 and 0 <= ray2d <= 1:
            return ray1d * np.linalg.norm(self.heading)
        return np.inf


@dataclass
class EdgeSweeperTeam(InstanceAutoNameRegistry):
    """Stores a set of shared variables between the members of sweeper team."""

    name: str = ''  # identifier used for registration in INSTANCES
    step_size: int_nm = 10_000  # largest step size allowed
    precision: int_nm = 1  # smallest step size allowed
    threshold: float = 0.1  # fraction of light_max that signals the edge
    light_max: int = -1  # maximum light observed at any point by any sweeper


default_edge_sweeper_team = EdgeSweeperTeam()


class EdgeSweeper(Sweeper):
    """Used to determine the edge of the stage based on camera feedback."""

    def __init__(self, origin: Vector2, heading: Vector2, team: str = '') -> None:
        self.history: list[Vector2] = []
        self.team = EdgeSweeperTeam.INSTANCES[team]
        super().__init__(origin, heading)

    def peak(self) -> int:
        """Return light (image sum) at current position, update light max."""
        light = int(_ctrl.get_image(header_keys=())[0].sum(dtype=np.int64))
        self.team.light_max = max(light, self.team.light_max)
        return light

    def goto(self, x: int_nm, y: int_nm) -> None:
        """Change sweeper position to `x`, `y` and update current position."""
        _ctrl.stage.set(x=x, y=y)
        self.history.append([x, y])
        self.position = np.array([x, y], dtype=float)

    def step(self, length: float_nm) -> None:
        """Change sweeper position by `length` in `heading` direction."""
        x0, y0 = _ctrl.stage.xy
        x1 = int(x0 + self.heading[0].item() * length)
        y1 = int(y0 + self.heading[1].item() * length)
        self.goto(x1, y1)


class MarchingEdgeSweeper(EdgeSweeper):
    """Moves monotonously, stops when intensity fract < max * threshold."""

    def sweep(self) -> None:
        """Walk steps into heading until peaked light is below threshold."""
        self.goto(x=int(self.origin[0]), y=int(self.origin[1]))
        light_here: int = self.peak()
        while light_here > self.team.light_max * self.team.threshold:
            self.step(length=self.team.step_size)
            light_here = self.peak()


class BinaryEdgeSweeper(EdgeSweeper):
    """A stage-state descriptor used to binary-search the grid edge."""

    def breed(self, other: Self) -> Self:
        """Return a new instance with mean heading and position."""
        o = (self.position + other.position) / 2
        n = np.linalg.norm(s := self.heading + other.heading)
        if n == 0:
            raise ValueError('Cannot breed sweepers with parallel heading')
        return self.__class__(origin=o, heading=s / n, team=self.team.name)

    def sweep(self) -> None:
        """Bin-search the edge based on peaked light vs max * threshold."""
        self.goto(x=int(self.origin[0]), y=int(self.origin[1]))
        step_size: float_nm = self.team.step_size
        direction: Literal[1, -1]
        refining: bool = False
        while step_size > self.team.precision:
            light_here = self.peak()
            if light_here > self.team.threshold * self.team.light_max:
                direction = 1
            else:
                direction = -1
                refining = True
            if refining:
                step_size *= 0.5
            self.step(length=direction * step_size)


def star_sweep(
    arms: Literal[3, 4, 5, 6, 7] = 5,
    order: Literal[1, 2, 3, 4, 5] = 5,
    offset: float_deg = 0,
) -> Generator[Vector2, None, None]:
    """Sweep window, yielding (x, y) points on its edge as they are found."""
    center: Vector2 = np.array(_ctrl.stage.xy, dtype=int)
    team = str(center)
    _ = EdgeSweeperTeam(name=team)

    # define and sweep with initial sweepers to approximate grid center (order=1)
    headings = offset + np.linspace(0, 360, num=arms, endpoint=False, dtype=float)
    directions = [versor(deg=h) for h in headings]
    bes = [BinaryEdgeSweeper(origin=center, heading=d, team=team) for d in directions]

    for sweeper in bes:
        sweeper.sweep()
        yield sweeper.position

    # For each order above 1, generate bisectors of previous orders, sweep, yield
    finished_bes = bes
    for _ in range(1, order):
        new_bes = []
        for a, b in pairwise(finished_bes, closed=True):
            ns = a.breed(b)
            ns.sweep()
            yield ns.position
            new_bes.append(ns)
        finished_bes = list(chain.from_iterable(zip(finished_bes, new_bes)))
