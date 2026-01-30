from __future__ import annotations

import queue
import tkinter as tk
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional


@dataclass
class _Call:
    name: str
    args: tuple
    kwargs: dict
    done: Optional[queue.Queue] = None  # for sync calls


class TkProxy:
    """Thread-safe proxy that runs target.methods in the main Tk thread."""

    def __init__(self, parent: tk.Misc, target: Any) -> None:
        self._tk = parent
        self._target = target
        self._q: queue.Queue[_Call] = queue.Queue()
        self._scheduled = False

    def _schedule(self) -> None:
        if not self._scheduled:
            self._scheduled = True
            self._tk.after(0, self._drain)

    def _drain(self) -> None:
        self._scheduled = False
        while True:
            try:
                c = self._q.get_nowait()
            except queue.Empty:
                break

            try:
                fn = getattr(self._target, c.name)
                res = fn(*c.args, **c.kwargs)
            except Exception as e:
                res = e

            if c.done is not None:
                c.done.put(res)

    def _post(
        self, name: str, *args: Any, done: Optional[queue.Queue] = None, **kwargs: Any
    ) -> None:
        self._q.put(_Call(name=name, args=args, kwargs=kwargs, done=done))
        self._schedule()

    def __getattr__(self, name: str) -> Callable[..., None]:
        """Get attribute (incl.

        methods) from proxy if unavailable in self.
        """

        try:
            return object.__getattribute__(self, name)
        except AttributeError as e:
            reraise_on_fail = e
            try:
                attr = getattr(self._target, name)
            except AttributeError:
                raise reraise_on_fail

        if not callable(attr):
            return attr

        @wraps(attr)
        def async_method(*args: Any, **kwargs: Any) -> None:
            self._post(name, *args, **kwargs)

        return async_method
