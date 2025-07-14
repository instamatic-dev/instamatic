from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from functools import wraps
from typing import Any, Iterator, NamedTuple, Optional, Protocol, Union

import numpy as np
from PIL import Image, ImageDraw

from instamatic.camera.videostream import VideoStream


class VideoStreamFrameProtocol(Protocol):
    auto_contrast: bool = True
    brightness: float = 1.0
    display_range: int = 255
    stream: VideoStream


class VideoStreamProcessor:
    """Additionally draw on top of frame by calling `PIL.ImageDraw` methods."""

    class DrawingOperation(NamedTuple):
        attr_name: str
        args: tuple
        kwargs: dict[str, Any]

    def __init__(self, vsf: VideoStreamFrameProtocol) -> None:
        self.vsf = vsf
        self._operations: deque = deque()  # Public deque of drawn elements
        self._overlay: Optional[Image.Image] = None  # Overlaid on call input
        self._drawing: Optional[ImageDraw.ImageDraw] = None  # Proxy for drawing
        self._last_operations_hash: Optional[int] = None  # Detecting changes
        self._temporary_frame: Optional[np.ndarray] = None

    def __getattr__(self, attr_name: str) -> Union[Any]:
        """Get the first of `self.attr_name` and `self._drawing.attr_name`.

        If the attribute is a _drawing callable, wrap it so that at `__call__`
        it is added to `self.operations` instead of being executed directly.
        Operations wrapped and called this way return `DrawingOperation` that
        can be deleted by calling `self.operations.remove(operation)`.
        """
        try:
            attr = object.__getattribute__(self, attr_name)
        except AttributeError as e:
            reraise_on_fail = e
            try:
                attr = getattr(self._drawing, attr_name)
            except AttributeError:
                raise reraise_on_fail

            if callable(attr):

                @wraps(attr)
                def wrapped(*args, **kwargs):
                    element = self.DrawingOperation(attr_name, args, kwargs)
                    self._operations.append(element)
                    return element

                return wrapped  # do not call attr - delay it until _redraw()
        return attr  # non-callable attr of self (if exists) or self._drawing

    @contextmanager
    def temporary_frame(self, frame: np.ndarray) -> Iterator[None]:
        """Temporarily switch self.frame to a different static `np.array`."""
        try:
            self._temporary_frame = frame
            yield
        finally:
            self._temporary_frame = None

    @property
    def frame(self) -> Union[np.ndarray, None]:
        """Request the raw numpy array frame from the current provider."""
        if (temporary_frame := self._temporary_frame) is not None:
            return temporary_frame
        return self.vsf.stream.frame

    @property
    def image(self) -> Union[Image.Image, None]:
        """Redraw overlay if `self.operations` changed, paste on the image."""
        if (frame := self.frame) is not None:
            # the display range in ImageTk is from 0 to 255
            if self.vsf.display_range != 255.0 or self.vsf.brightness != 1.0:
                if self.vsf.auto_contrast:
                    display_range = 1 + np.percentile(frame[::4, ::4], 99.5)
                else:
                    display_range = self.vsf.display_range
                frame = (self.vsf.brightness * 255 / display_range) * frame
            frame = np.clip(frame.astype(np.int16), 0, 255).astype(np.uint8)
        image = Image.fromarray(frame)
        if self._overlay is None:
            self._initialize_overlay(image.size)
        if self._operations_deque_changed():
            self._redraw()
        bbox = self._overlay.getbbox(alpha_only=True)
        if bbox:
            bbox_contents = self._overlay.crop(bbox)
            image.paste(bbox_contents, box=bbox, mask=bbox_contents)
        return image

    def _initialize_overlay(self, size: tuple[int, int]) -> None:
        """Initialize `self._overlay` image and `self._drawing` proxy."""
        self._overlay = Image.new('RGBA', size, (255, 255, 255, 0))
        self._drawing = ImageDraw.Draw(self._overlay)

    def _operations_deque_changed(self):
        if c := (h := hash(repr(self._operations))) != self._last_operations_hash:
            self._last_operations_hash = h
        return c

    def _redraw(self) -> None:
        """Clear and reapply all `DrawingOperation`s in `self.operations`."""
        self._overlay.paste(im=(255, 255, 255, 0), box=(0, 0, *self._overlay.size))
        for attr_name, args, kwargs in self.operations:
            draw_method = getattr(self._drawing, attr_name)
            draw_method(*args, **kwargs)

    def circle(
        self,
        xy: tuple[int, int],
        radius: float,
        fill: Union[str, tuple] = None,
        outline: Union[str, tuple] = None,
        width: int = 1,
    ) -> None:
        """Circle was added in v10.4.0 so port it from v11.1.0 to be sure."""
        ellipse_xy = (xy[0] - radius, xy[1] - radius, xy[0] + radius, xy[1] + radius)
        self.ellipse(ellipse_xy, fill=fill, outline=outline, width=width)
