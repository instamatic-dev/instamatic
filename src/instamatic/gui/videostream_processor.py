from __future__ import annotations

import io
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
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

    @dataclass
    class Instruction:
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
                    instruction = self.Instruction(attr_name, args, kwargs)
                    self.instructions.append(instruction)
                    return instruction

                return wrapped  # do not call attr - delay it until _redraw()
        return attr  # non-callable attr of self (if exists) or self._drawing

    def on(self, image: Image.Image) -> Image.Image:
        """Core method: draws all deferred `self.instructions` on image."""
        self._drawing = ImageDraw.Draw(image)
        for ins in self.instructions:
            getattr(self._drawing, ins.attr_name)(*ins.args, **ins.kwargs)
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
    """Encapsulate complex `VideoStreamFrame` frame/image processing.

    This class handles converting mathematical operations behind efficiently
    converting raw frames into images, rendering matplotlib figures as static
    images in the video stream window, as well as drawing on top of images.

    Streamed view can be altered by setting a temporary frame/image/figure.
    Each of these can be set/reset via corresponding attribute, or set
    temporarily via `with processor.temporary(frame/image/figure=...)` syntax.

    Drawing is handled via the `draw` attribute of the `DeferredImageDraw`
    class which acts as a deferred proxy for PIL.ImageDraw. Instructions,
    instead of being applied directly on one frame only, are saved into the
    `draw.instructions` deque and efficiently re-applied continuously.
    """

    def __init__(self, vsf: VideoStreamFrameProtocol) -> None:
        self.vsf: VideoStreamFrameProtocol = vsf
        self.draw: DeferredImageDraw = DeferredImageDraw()
        self.color_mode: Literal['L', 'RGB'] = 'RGB'
        self.temporary_frame: Optional[np.ndarray] = None
        self.temporary_image: Optional[PIL.Image.Image] = None
        self._temporary_figure: Optional[Figure] = None

    @property
    def frame(self) -> Union[np.ndarray, None]:
        """The raw `np.ndarray` frame from the stream or `_temporary_frame`"""
        if (temporary_frame := self.temporary_frame) is not None:
            return temporary_frame
        return self.vsf.stream.frame

    @property
    def image(self) -> Union[Image.Image, None]:
        """Processed image with `draw.instructions`, or `_temporary_image`."""
        if (temporary_image := self.temporary_image) is not None:
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

    def render_figure(self, figure: Figure) -> PIL.Image.Image:
        """Convert a `Figure` into a `Image` to allow a temporary render in
        GUI."""
        buffer = io.BytesIO()
        dpi = min(self.vsf.stream.frame.shape / figure.get_size_inches())
        figure.savefig(buffer, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0)
        buffer.seek(0)
        return Image.open(buffer).convert('RGBA')

    @contextmanager
    def temporary(
        self,
        *,
        frame: Optional[np.ndarray] = None,
        image: Optional[PIL.Image.Image] = None,
        figure: Optional[Figure] = None,
    ) -> Iterator[None]:
        """Temporarily set alt temporary_frame/image via `with` statement."""
        pre_context_values = self.temporary_frame, self.temporary_image
        try:
            if frame is not None:
                self.temporary_frame = frame
            if image is not None:
                self.temporary_image = image
            elif figure is not None:
                self.temporary_image = self.render_figure(figure)
            yield
        finally:
            self.temporary_frame, self.temporary_image = pre_context_values

    @property
    def temporary_figure(self) -> Figure:
        return self._temporary_figure

    @temporary_figure.setter
    def temporary_figure(self, figure: Union[Figure, None]) -> None:
        self._temporary_figure = figure
        self.temporary_image = self.render_figure(figure) if figure else None
