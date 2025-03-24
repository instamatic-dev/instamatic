from __future__ import annotations

import atexit
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, List, Optional, Type, TypeVar, Union

import numpy as np

from instamatic.camera import Camera
from instamatic.camera.camera_base import CameraBase
from instamatic.image_utils import autoscale


@dataclass(frozen=True)
class MediaRequest:
    n_frames: Optional[int] = None
    exposure: Optional[float] = None
    binsize: Optional[int] = None


class ImageRequest(MediaRequest):
    """To be used when requesting a single image via `get_image`"""


class MovieRequest(MediaRequest):
    """To be used when requesting an image series via `get_movie`"""


class MediaGrabber:
    """Continuously read out the camera for continuous acquisition.

    When the continousCollectionEvent is set, the camera will set the
    exposure to `frametime`, otherwise, the default camera exposure is
    used.

    The callback function is used to send the media, either image or movie,
    back to the parent routine.
    """

    def __init__(self, cam: CameraBase, callback, frametime: float = 0.05):
        super().__init__()

        self.callback = callback
        self.cam = cam

        self.default_exposure = self.cam.default_exposure
        self.default_binsize = self.cam.default_binsize
        self.dimensions = self.cam.dimensions
        self.name = self.cam.name

        self.frame = None
        self.thread = None
        self.stopEvent = None

        self.stash = None

        self.frametime = frametime
        self.request: Optional[MediaRequest] = None
        self.requested_media = None
        self.lock = threading.Lock()

        self.stopEvent = threading.Event()
        self.acquireInitiateEvent = threading.Event()
        self.acquireCompleteEvent = threading.Event()
        self.continuousCollectionEvent = threading.Event()

    def run(self):
        while not self.stopEvent.is_set():
            if self.acquireInitiateEvent.is_set():
                r = self.request
                self.acquireInitiateEvent.clear()
                e = r.exposure if r.exposure else self.default_exposure
                b = r.binsize if r.binsize else self.default_binsize
                if isinstance(r, ImageRequest):
                    media = self.cam.get_image(exposure=e, binsize=b)
                else:  # isinstance(r, MovieRequest):
                    n = r.n_frames if r.n_frames else 1
                    media = self.cam.get_movie(n_frames=n, exposure=e, binsize=b)
                self.callback(media, request=r)

            elif not self.continuousCollectionEvent.is_set():
                frame = self.cam.get_image(
                    exposure=self.frametime, binsize=self.default_binsize
                )
                self.callback(frame, request=None)

    def start_loop(self):
        self.thread = threading.Thread(target=self.run, args=(), daemon=True)
        self.thread.start()

    def stop(self):
        self.stopEvent.set()
        self.thread.join()


_VS = TypeVar('_VS', bound='VideoStream')


class VideoStream(threading.Thread):
    """Base interface for collecting preview and media from passed camera."""

    def __new__(cls: Type[_VS], cam: Union[CameraBase, str] = 'simulate') -> _VS:
        """Create VideoStream subclass based on passed cam stream-ability."""
        if cls is VideoStream:
            cam: CameraBase = Camera(name=cam) if isinstance(cam, str) else cam
            subclass = LiveVideoStream if cam.streamable else FakeVideoStream
            video_stream = super(VideoStream, subclass).__new__(subclass)
            video_stream.cam = cam
            return video_stream
        return super().__new__(cls)

    def __init__(self, cam: Union[CameraBase, str] = 'simulate') -> None:
        threading.Thread.__init__(self)

        if not hasattr(self, 'cam') or not isinstance(self.cam, CameraBase):
            self.cam: CameraBase = Camera(name=cam) if isinstance(cam, str) else cam
        self.lock = threading.Lock()

        self.default_exposure = self.cam.default_exposure
        self.default_binsize = self.cam.default_binsize
        self.dimensions = self.cam.dimensions
        self.name = self.cam.name

        self.frametime = self.default_exposure

        self.frame = NotImplemented
        self.grabber = NotImplemented

    def __getattr__(self, attr_name: str) -> Any:
        """Pass attribute lookups to self.cam to prevent AttributeError."""
        try:
            return object.__getattribute__(self, attr_name)
        except AttributeError as e:
            reraise_on_fail = e
            if attr_name == 'cam':
                return
            try:
                return getattr(self.cam, attr_name)
            except AttributeError:
                raise reraise_on_fail

    def close(self):
        pass

    def block(self):
        pass

    def unblock(self):
        pass

    @contextmanager
    def blocked(self):
        yield



class LiveVideoStream(VideoStream):
    """Handle the continuous stream of incoming data from the ImageGrabber."""

    def __init__(self, cam: Union[CameraBase, str] = 'simulate') -> None:
        super().__init__(cam)
        self.frame = None
        self.grabber = self.setup_grabber()
        self.start()

    def start(self):
        self.grabber.start_loop()

    def send_media(
        self,
        media: Union[np.ndarray, List[np.ndarray]],
        request: Optional[MediaRequest] = None,
    ) -> None:
        """Callback function of `self.grabber` that handles grabbed media."""
        with self.grabber.lock:
            if request is None:
                self.frame = media
            elif isinstance(request, ImageRequest):
                self.requested_media = self.frame = media
                self.grabber.acquireCompleteEvent.set()
            else:  # isinstance(request, MovieRequest):
                self.requested_media = media
                self.frame = media[-1]
                self.grabber.acquireCompleteEvent.set()

    def setup_grabber(self) -> MediaGrabber:
        grabber = MediaGrabber(self.cam, callback=self.send_media, frametime=self.frametime)
        atexit.register(grabber.stop)
        return grabber

    def get_image(self, exposure=None, binsize=None):
        request = ImageRequest(exposure=exposure, binsize=binsize)
        return self._get_media(request)

    def get_movie(self, n_frames: int, exposure=None, binsize=None):
        request = MovieRequest(n_frames=n_frames, exposure=exposure, binsize=binsize)
        return self._get_media(request)

    def _get_media(self, request: MediaRequest) -> Union[np.ndarray, List[np.ndarray]]:
        with self.blocked():  # Stop the passive collection during request acquisition
            self.grabber.request = request
            self.grabber.acquireInitiateEvent.set()
            self.grabber.acquireCompleteEvent.wait()
            with self.grabber.lock:
                media = self.requested_media
                self.requested_media = None
            self.grabber.request = None
            self.grabber.acquireCompleteEvent.clear()
        return media

    def update_frametime(self, frametime):
        self.frametime = frametime
        self.grabber.frametime = frametime

    def close(self):
        self.grabber.stop()

    def block(self):
        self.grabber.continuousCollectionEvent.set()

    def unblock(self):
        self.grabber.continuousCollectionEvent.clear()

    @contextmanager
    def blocked(self):
        """Set `continuousCollectionEvent` within the statement scope only."""
        was_set_before = self.grabber.continuousCollectionEvent.is_set()
        self.grabber.continuousCollectionEvent.set()
        yield
        if not was_set_before:
            self.grabber.continuousCollectionEvent.clear()

    def show_stream(self):
        from instamatic.gui import videostream_frame

        t = threading.Thread(target=videostream_frame.start_gui, args=(self,), daemon=True)
        t.start()


class FakeVideoStream(VideoStream):
    """Allows displaying the image in GUI by faking a continuous signal."""

    def __init__(self, cam: Union[CameraBase, str] = 'simulate') -> None:
        super().__init__(cam)
        self.display_dim = 512
        self.frame, _ = autoscale(np.ones(self.dimensions), maxdim=self.display_dim)

    def get_image(self, exposure=None, binsize=None):
        frame = self.cam.get_image(exposure=exposure, binsize=binsize)
        self.frame, _ = autoscale(frame, maxdim=self.display_dim)
        return frame

    def get_movie(self, n_frames: int, exposure=None, binsize=None):
        frames = self.cam.get_movie(n_frames=n_frames, exposure=exposure, binsize=binsize)
        self.frame, _ = autoscale(frames[0], maxdim=self.display_dim)
        return frames

    def update_frametime(self, frametime):
        self.frametime = frametime

    def show_stream(self):
        from instamatic.gui import videostream_frame

        t = threading.Thread(target=videostream_frame.start_gui, args=(self,), daemon=False)
        t.start()


if __name__ == '__main__':
    stream = LiveVideoStream(cam='timepix')
    from IPython import embed

    embed()
    stream.stop()
