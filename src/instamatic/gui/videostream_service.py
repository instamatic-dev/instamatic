from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator, Optional, Tuple, Union

try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol  # fallback for Python < 3.8

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Colormap
from PIL import Image, ImageDraw, ImageEnhance

from instamatic.collections import NoOverwriteDict, SubclassRegistryMeta

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


class VideoStreamEnhancerProtocol(Protocol):
    """Interface for sequential VideoStream image editors."""

    active: bool  # will edit provided `PIL.Image` if active = True
    precedence: int  # all enhancers are called in decreasing precedence order

    def __call__(self, image: Image.Image) -> Image.Image:
        """Edit the `PIL.Image.Image` and return its modified version."""
        ...


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~ VIDEO STREAM SERVICE ~~~~~~~~~~~~~~~~~~~~~~~~~~~ #


def precedence_key(p: Union[VideoStreamEditorProtocol, VideoStreamEnhancerProtocol]) -> float:
    return -getattr(p, 'precedence', float('inf'))


class VideoStreamService:
    """Service managing video providers and editors for VideoStreamFrame."""

    def __init__(self, provider: VideoStreamProviderProtocol) -> None:
        self.provider = provider
        self.editors: NoOverwriteDict[str, VideoStreamEditorProtocol] = NoOverwriteDict()
        self.enhancers: NoOverwriteDict[str, VideoStreamEnhancerProtocol] = NoOverwriteDict()
        self.last_frame: Optional[np.ndarray] = None

    def add_editor(self, name: str, editor: VideoStreamEditorProtocol) -> None:
        """Convenience method that adds a new `VideoStreamEditorProtocol`"""
        self.editors[name] = editor

    def add_enhancer(self, name: str, enhancer: VideoStreamEnhancerProtocol) -> None:
        """Convenience method that adds a new `VideoStreamEnhancerProtocol`"""
        self.enhancers[name] = enhancer

    @property
    def frame(self) -> Union[np.ndarray, None]:
        """Request the raw numpy array frame from the current provider."""
        self.last_frame = frame = self.provider()
        return frame

    @property
    def image(self) -> Union[Image.Image, None]:
        """The last `self.frame` edited & enhanced in each precedence order."""
        array = self.last_frame
        if array is None:
            return None
        for editor in sorted(self.editors.values(), key=precedence_key):
            if getattr(editor, 'active', True):
                array = editor(array)
        image = Image.fromarray((255.0 * array).astype(np.uint8))
        for enhancer in sorted(self.enhancers.values(), key=precedence_key):
            if getattr(enhancer, 'active', True):
                image = enhancer(image)
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


class VideoStreamEnhancer(metaclass=SubclassRegistryMeta):
    """Base class for enhancers; handle `PIL.Image.Image`s."""

    active = True
    precedence = 0


class ImageEnhanceEnhancer(VideoStreamEnhancer):
    """Use `PIL.ImageEnhance` methods to enhance features on the fresh
    image."""

    precedence = 2_000_000

    def __init__(self, videostream_frame) -> None:
        self.vsf = videostream_frame

    def __call__(self, image: Image.Image) -> Image.Image:
        brightness = self.vsf.brightness
        if brightness != 1:
            image = ImageEnhance.Brightness(image).enhance(brightness)
        # see also ImageEnhance.Color, ImageEnhance.Sharpness, ImageEnhance.Contrast
        return image


class DrawnOverlayEnhancer(VideoStreamEnhancer):
    """Use `PIL.ImageDraw` methods to draw overlay over the received image."""

    precedence = 2_000

    def __init__(self) -> None:
        self._overlay: Optional[Image.Image] = None
        self._drawing: Optional[ImageDraw.ImageDraw] = None

    def __getattr__(self, attr_name: str) -> Any:
        """Automatically pass calls to underlying `PIL.ImageDraw.ImageDraw`"""
        print('getting ' + attr_name)
        try:
            object.__getattribute__(self, attr_name)
        except AttributeError as e:
            reraise_on_fail = e
            try:
                return getattr(self._drawing, attr_name)
            except AttributeError:
                raise reraise_on_fail

    def __call__(self, image: Image.Image) -> Image.Image:
        if self._overlay is None:
            self._overlay = Image.new('RGBA', image.size, (255, 255, 255, 0))
            self._drawing = ImageDraw.Draw(self._overlay)
        bbox = self._overlay.getbbox(alpha_only=True)
        if bbox:
            bbox_contents = self._overlay.crop(bbox)
            image.paste(bbox_contents, box=bbox, mask=bbox_contents)
        return image

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
        self._drawing.ellipse(ellipse_xy, fill=fill, outline=outline, width=width)
