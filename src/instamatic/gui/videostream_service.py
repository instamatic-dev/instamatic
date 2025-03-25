from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from functools import lru_cache, wraps
from typing import Any, Dict, Iterator, NamedTuple, Optional, Tuple, Union

try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol  # fallback for Python < 3.8

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Colormap
from PIL import Image, ImageDraw, ImageEnhance

from instamatic._collections import NoOverwriteDict, SubclassRegistryMeta

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ PROTOCOLS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


class VideoStreamProviderProtocol(Protocol):
    """Protocol defining interface for suppliers of raw VideoStream frames."""

    def __call__(self) -> np.ndarray:
        """Provide a raw frame as a 2D or 3D np.ndarray (color on last axes)"""
        ...


class VideoStreamEditorProtocol(Protocol):
    """Interface for sequential VideoStream `np.ndarray` array editors."""

    active: bool  # will edit provided `np.ndarray` if active = True
    precedence: int  # all editors are called in decreasing precedence order

    def __call__(self, array: np.ndarray) -> np.ndarray:
        """Edit the `np.ndarray` and return its modified version."""
        ...


class VideoStreamOverlayProtocol(Protocol):
    """Interface for sequential VideoStream image editors."""

    active: bool  # will edit provided `PIL.Image` if active = True
    precedence: int  # all overlays are called in decreasing precedence order

    def __call__(self, image: Image.Image) -> Image.Image:
        """Edit the `PIL.Image.Image` and return its modified version."""
        ...


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~ VIDEO STREAM SERVICE ~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def precedence_key(p: Union[VideoStreamEditorProtocol, VideoStreamOverlayProtocol]) -> float:
    return -getattr(p, 'precedence', float('inf'))


class VideoStreamService:
    """Service managing `VideoStreamFrame` providers, editors and overlays."""

    def __init__(self, provider: VideoStreamProviderProtocol) -> None:
        self.provider = provider
        self.editors: NoOverwriteDict[str, VideoStreamEditorProtocol] = NoOverwriteDict()
        self.overlays: NoOverwriteDict[str, VideoStreamOverlayProtocol] = NoOverwriteDict()
        self.last_frame: Optional[np.ndarray] = None

    def add_editor(self, name: str, editor: VideoStreamEditorProtocol) -> None:
        """Convenience method that adds a new `VideoStreamEditorProtocol`"""
        self.editors[name] = editor

    def add_overlay(self, name: str, overlay: VideoStreamOverlayProtocol) -> None:
        """Convenience method that adds a new `VideoStreamOverlayProtocol`"""
        self.overlays[name] = overlay

    @property
    def frame(self) -> Union[np.ndarray, None]:
        """Request the raw numpy array frame from the current provider."""
        self.last_frame = frame = self.provider()
        return frame

    @property
    def image(self) -> Union[Image.Image, None]:
        """The last `self.frame` edited & overlaid in each precedence order."""
        array = self.last_frame
        if array is None:
            return None
        for editor in sorted(self.editors.values(), key=precedence_key):
            if getattr(editor, 'active', True):
                array = editor(array)
        image = Image.fromarray((255.0 * array).astype(np.uint8))
        for overlay in sorted(self.overlays.values(), key=precedence_key):
            if getattr(overlay, 'active', True):
                image = overlay(image)
        return image

    @contextmanager
    def temporary_provider(self, provider: VideoStreamProviderProtocol) -> Iterator[None]:
        """Temporarily switch to a different VideoStreamProvider."""
        permanent_provider, self.provider = self.provider, provider
        try:
            yield
        finally:
            self.provider = permanent_provider


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~ VIDEO STREAM EDITORS ~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


class VideoStreamEditor(metaclass=SubclassRegistryMeta):
    """Base class for editors; handled arrays should be normalized to [0, 1]"""

    active = True
    precedence = 0


class Normalize2DEditor(VideoStreamEditor):
    """Scale a 2D frame based on contrast setting and normalize it to [0, 1]"""

    precedence = 5_000_000

    def __init__(self, videostream_frame) -> None:
        self.vsf = videostream_frame

    def __call__(self, array: np.ndarray) -> np.ndarray:
        if self.vsf.auto_contrast:
            range_ = 1 + np.percentile(array[::4, ::4], 99.5)
        else:
            range_ = self.vsf.display_range
        return np.clip(array, 0, range_) / range_


class Colorize2DEditor(VideoStreamEditor):
    """Convert a 2D grayscale frame to 3D RGB, optionally using a colormap."""

    precedence = 2_000_000

    def __init__(self, colormap_name: Optional[str]) -> None:
        self.colormap_name = colormap_name  # note: colormaps can be a bit slow

    @lru_cache(maxsize=5)
    def _get_colormap(self, colormap_name: str) -> Colormap:
        return plt.colormaps[colormap_name]

    @property
    def colormap(self) -> Union[Colormap, None]:
        return self._get_colormap(self.colormap_name)

    def __call__(self, array: np.ndarray) -> np.ndarray:
        if self.colormap_name is None:
            array = np.stack([array] * 3, axis=-1)  # faster than cmap & PIL
        else:
            array = self.colormap(array)
        return array


# ~~~~~~~~~~~~~~~~~~~~~~~~~~ VIDEO STREAM ENHANCERS ~~~~~~~~~~~~~~~~~~~~~~~~~~ #


class VideoStreamOverlay(metaclass=SubclassRegistryMeta):
    """Base class for overlays; handle `PIL.Image.Image`s."""

    active = True
    precedence = 0


class ImageEnhanceOverlay(VideoStreamOverlay):
    """Use `PIL.ImageEnhance` methods to enhance features of the image."""

    precedence = 2_000_000

    def __init__(self, videostream_frame) -> None:
        self.vsf = videostream_frame

    def __call__(self, image: Image.Image) -> Image.Image:
        brightness = self.vsf.brightness
        if brightness != 1:
            image = ImageEnhance.Brightness(image).enhance(brightness)
        # see also ImageEnhance.Color, ImageEnhance.Sharpness, ImageEnhance.Contrast
        return image


class ImageDrawOverlay(VideoStreamOverlay):
    """Use `PIL.ImageDraw` methods to draw on top of the image."""

    precedence = 2_000

    class DrawingOperation(NamedTuple):
        attr_name: str
        args: Tuple
        kwargs: Dict[str, Any]

    def __init__(self) -> None:
        self.operations: deque = deque()  # Public deque of `DrawnElement`s
        self._overlay: Optional[Image.Image] = None  # Overlaid on call input
        self._drawing: Optional[ImageDraw.ImageDraw] = None  # Proxy for drawing
        self._last_elements_hash: Optional[int] = None  # For detecting changes

        # Note: `__getattr__` returns op;  to remove it

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
                    self.operations.append(element)
                    return element

                return wrapped  # do not call attr - delay it until _redraw()
        return attr  # non-callable attr of self (if exists) or self._drawing

    def __call__(self, image: Image.Image) -> Image.Image:
        """Redraw overlay if `self.operations` changed, paste on the image."""
        if self._overlay is None:
            self._initialize_overlay(image.size)

        # Detect modifications to self.elements and _redraw() if needed.
        current_elements_hash = hash(repr(self.operations))
        if current_elements_hash != self._last_elements_hash:
            self._redraw()
            self._last_elements_hash = current_elements_hash

        bbox = self._overlay.getbbox(alpha_only=True)
        if bbox:
            bbox_contents = self._overlay.crop(bbox)
            image.paste(bbox_contents, box=bbox, mask=bbox_contents)
        return image

    def _initialize_overlay(self, size: Tuple[int, int]) -> None:
        """Initialize `self._overlay` image and `self._drawing` proxy."""
        self._overlay = Image.new('RGBA', size, (255, 255, 255, 0))
        self._drawing = ImageDraw.Draw(self._overlay)

    def _redraw(self) -> None:
        """Clear and reapply all `DrawingOperation`s in `self.operations`."""
        self._overlay.paste(im=(255, 255, 255, 0), box=(0, 0, *self._overlay.size))
        for attr_name, args, kwargs in self.operations:
            draw_method = getattr(self._drawing, attr_name)
            draw_method(*args, **kwargs)

    def circle(
        self,
        xy: Tuple[int, int],
        radius: float,
        fill: Union[str, Tuple] = None,
        outline: Union[str, Tuple] = None,
        width: int = 1,
    ) -> None:
        """Circle was added in v10.4.0 so port it from v11.1.0 to be sure."""
        ellipse_xy = (xy[0] - radius, xy[1] - radius, xy[0] + radius, xy[1] + radius)
        self.ellipse(ellipse_xy, fill=fill, outline=outline, width=width)
