from __future__ import annotations

import io
from collections import deque
from contextlib import contextmanager
from functools import wraps
from typing import Any, Iterator, Literal, NamedTuple, Optional, Protocol, Union

import numpy as np
import PIL.Image
from matplotlib.figure import Figure
from PIL import Image, ImageDraw

from instamatic.camera.videostream import VideoStream


class VideoStreamFrameProtocol(Protocol):
    """Mimics the `VideoStreamFrame` interface to avoid circular import."""

    auto_contrast: bool = True
    brightness: float = 1.0
    display_range: int = 255
    stream: VideoStream


class DeferredImageDraw:
    """Defer `ImageDraw` method calls: put them in deque, draw using `on`."""

    class Instruction(NamedTuple):
        """Stores info about `ImageDraw` calls deferred by `__getattr__`."""

        attr_name: str
        args: tuple
        kwargs: dict[str, Any]

    def __init__(self, draw: Optional[ImageDraw] = None) -> None:
        self._drawing = draw if draw else ImageDraw.Draw(Image.new('RGB', (1, 1)))
        self.instructions: deque[DeferredImageDraw.Instruction] = deque()

    def __getattr__(self, attr_name: str) -> Union[Any]:
        """Get the first of `self.attr_name` and `self._drawing.attr_name`.

        If the attribute is a _drawing callable, wrap it so that at call
        it is added to `self.instructions` instead of being executed directly.
        `DeferredImageDraw.Instruction` instance created this way is returned
        and can be deleted by calling `self.instructions.remove(instruction)`.
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
                def wrapped(*args, **kwargs) -> DeferredImageDraw.Instruction:
                    element = self.Instruction(attr_name, args, kwargs)
                    self.instructions.append(element)
                    return element

                return wrapped  # do not call attr - delay it until _redraw()
        return attr  # non-callable attr of self (if exists) or self._drawing

    def on(self, image: Image.Image) -> Image.Image:
        """Core method: draws all deferred `self.instructions` on image."""
        self._drawing = ImageDraw.Draw(image)
        for attr_name, args, kwargs in self.instructions:
            getattr(self._drawing, attr_name)(*args, **kwargs)
        return image

    def circle(
        self,
        xy: tuple[int, int],
        radius: float,
        fill: Union[str, tuple] = None,
        outline: Union[str, tuple] = None,
        width: int = 1,
    ) -> DeferredImageDraw.Instruction:
        """Circle was only added to PIL in v10.4.0, so port it to be safe."""
        ellipse_xy = (xy[0] - radius, xy[1] - radius, xy[0] + radius, xy[1] + radius)
        return self.ellipse(ellipse_xy, fill=fill, outline=outline, width=width)


class VideoStreamProcessor:
    """Encapsulate complex `VideoStreamFrame` frame/image processing."""

    def __init__(self, vsf: VideoStreamFrameProtocol) -> None:
        self.vsf: VideoStreamFrameProtocol = vsf
        self.draw: DeferredImageDraw = DeferredImageDraw()
        self.color_mode: Literal['L', 'RGB'] = 'RGB'
        self._temporary_frame: Optional[np.ndarray] = None
        self._temporary_image: Optional[PIL.Image.Image] = None

    @property
    def frame(self) -> Union[np.ndarray, None]:
        """The raw `np.ndarray` frame from the stream or `_temporary_frame`"""
        if (temporary_frame := self._temporary_frame) is not None:
            return temporary_frame
        return self.vsf.stream.frame

    @property
    def image(self) -> Union[Image.Image, None]:
        """Processed image with `draw.instructions`, or `_temporary_image`."""
        if (temporary_image := self._temporary_image) is not None:
            return temporary_image
        if (frame := self.frame) is not None:
            if self.vsf.display_range != 255.0 or self.vsf.brightness != 1.0:
                if self.vsf.auto_contrast:
                    display_range = 1 + np.percentile(frame[::4, ::4], 99.5)
                else:
                    display_range = self.vsf.display_range
                frame = (self.vsf.brightness * 255 / display_range) * frame
            frame = np.clip(frame.astype(np.int16), 0, 255).astype(np.uint8)
        if self.draw.instructions:
            image = Image.fromarray(frame).convert(self.color_mode)
            self.draw.on(image)
        else:
            image = Image.fromarray(frame)
        return image

    @contextmanager
    def temporary_frame(self, frame: np.ndarray) -> Iterator[None]:
        """Temporarily set `self.frame` to show a static `np.ndarray`."""
        try:
            self._temporary_frame = frame
            yield
        finally:
            self._temporary_frame = None

    @contextmanager
    def temporary_image(self, image: PIL.Image.Image) -> Iterator[None]:
        """Temporarily set `self.image` to show a static `PIL.Image.Image`."""
        try:
            self._temporary_image = image
            yield
        finally:
            self._temporary_image = None

    @contextmanager
    def temporary_figure(self, figure: Figure) -> Iterator[None]:
        """Temporarily set `self.image`: show a static `mpl.figure.Figure`."""
        buffer = io.BytesIO()
        dpi = min(self.vsf.stream.frame.shape / figure.get_size_inches())
        figure.savefig(buffer, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0)
        buffer.seek(0)
        with self.temporary_image(Image.open(buffer).convert('RGBA')):
            yield
