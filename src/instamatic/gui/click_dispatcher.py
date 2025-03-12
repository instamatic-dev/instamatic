from __future__ import annotations

import enum
import queue
from typing import Callable, Optional, Union

from typing_extensions import Self

from instamatic.collections import NoOverwriteDict


class MouseButton(enum.IntEnum):
    LEFT = 1
    MIDDLE = 2
    RIGHT = 3


class ClickEvent:
    """Individual click event expected and handled by `ClickListener`s."""

    def __init__(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: Optional[int] = None,
    ) -> None:
        self.x = x if x else 0
        self.y = y if y else 0
        self.button = MouseButton(button) if button else MouseButton.LEFT


class ClickListener:
    """Request clicks and call `callback` on each received."""

    def __init__(
        self,
        name: str,
        callback: Optional[Callable[[ClickEvent], None]] = None,
    ) -> None:
        self.name = name
        self.callback = callback
        self.queue = queue.Queue()
        self.active = False

    def __enter__(self) -> Self:
        self.queue.queue.clear()
        self.active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.active = False

    def handle_click(self, click_event: ClickEvent) -> None:
        if self.active:
            if self.callback is not None:
                self.callback(click_event)
            self.queue.put(click_event)

    def get_click(self, timeout: float = None) -> Union[ClickEvent, None]:
        """Get next `ClickEvent` from the queue or await it until `timeout`"""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None


class ClickDispatcher:
    """Manages `ClickEvent` distribution across `ClickListeners`."""

    def __init__(self):
        self.listeners: NoOverwriteDict[str, ClickListener] = NoOverwriteDict()

    @property
    def active(self) -> bool:
        return any(listener.active for listener in self.listeners.values())

    def add_listener(
        self,
        name: str,
        callback: Optional[Callable[[ClickEvent], None]] = None,
    ) -> ClickListener:
        """Convenience method that adds and returns a new `ClickListener`"""
        listener = ClickListener(name, callback)
        self.listeners[name] = listener
        return listener

    def handle_click(self, *args, **kwargs) -> None:
        """Call `handle_click` method of every active `ClickListener`"""
        event = ClickEvent(*args, **kwargs)
        for listener in self.listeners.values():
            if listener.active:
                listener.handle_click(event)
