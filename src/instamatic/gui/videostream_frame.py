from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import *
from tkinter import Label as TkLabel
from tkinter.ttk import *
from typing import Optional, Union

import numpy as np
from PIL import Image, ImageTk
from PIL.Image import Resampling

from instamatic._typing import AnyPath
from instamatic.formats import read_tiff, write_tiff
from instamatic.gui.base_module import BaseModule, HasQMixin
from instamatic.gui.click_dispatcher import ClickDispatcher
from instamatic.gui.videostream_processor import VideoStreamProcessor
from instamatic.processing import apply_flatfield_correction
from instamatic.utils.spinbox import Spinbox


class VideoStreamFrame(LabelFrame, HasQMixin):
    """GUI panel to continuously display the last frame streamed from the
    camera."""

    def __init__(self, parent, stream, app=None):
        LabelFrame.__init__(self, parent, text='Stream')

        self.parent = parent

        self.stream = stream
        self.app = app

        self.panel = None

        self.frame_delay = 50

        self.frametime = 0.05
        self.brightness = 1.0
        self.display_range = self.display_range_default = self.stream.cam.dynamic_range
        # Maximum number from image readout

        self.auto_contrast = True

        self.resize_image = False

        self.last = time.perf_counter()
        self.nframes = 1
        self.update_frequency = 0.25
        self.last_interval = self.frametime

        self._atexit_funcs = []

        #######################

        self.parent = parent

        self.init_vars()
        self.buttonbox(self)
        self.header(self)
        self.makepanel(self)

        try:
            self.parent.wm_title('Video stream')
            self.parent.wm_protocol('WM_DELETE_WINDOW', self.close)
        except AttributeError:
            pass

        self.parent.bind('<Escape>', self.close)

        self.start_stream()

        self.click_dispatcher = ClickDispatcher()
        self.panel.bind('<Button>', self.on_click)
        self.processor = VideoStreamProcessor(self)

    def init_vars(self):
        self.var_fps = DoubleVar()
        self.var_interval = DoubleVar()
        # self.var_overhead = DoubleVar()

        self.var_frametime = DoubleVar()
        self.var_frametime.set(self.frametime)
        self.var_frametime.trace_add('write', self.update_frametime)

        self.var_brightness = DoubleVar(value=self.brightness)
        self.var_brightness.trace_add('write', self.update_brightness)

        self.var_display_range = DoubleVar(value=self.display_range_default)
        self.var_display_range.trace_add('write', self.update_display_range)

        self.var_resize_image = BooleanVar(value=self.resize_image)
        self.var_resize_image.trace_add('write', self.update_resize_image)

        self.var_auto_contrast = BooleanVar(value=self.auto_contrast)
        self.var_auto_contrast.trace_add('write', self.update_auto_contrast)

    def buttonbox(self, master):
        btn_frame = Frame(master)
        btn_frame.pack(side='bottom', fill=BOTH, padx=10, pady=10)
        btn1 = Button(btn_frame, text='Save frame', command=self.save_frame)
        btn1.pack(side=LEFT, expand=True, fill='both')
        btn2 = Button(btn_frame, text='Save image', command=self.save_image)
        btn2.pack(side=LEFT, expand=True, fill='both')

    @property
    def frame(self) -> Union[np.ndarray, None]:
        """Raw image frame from the camera."""
        return self.processor.frame

    def header(self, master):
        ewidth = 8
        lwidth = 12

        frame = Frame(master)

        self.cb_resize = Checkbutton(
            frame, text='Increase size', variable=self.var_resize_image
        )
        self.cb_resize.grid(row=1, column=4)

        self.cb_contrast = Checkbutton(
            frame, text='Auto contrast', variable=self.var_auto_contrast
        )
        self.cb_contrast.grid(row=1, column=5)

        self.e_fps = Entry(frame, width=lwidth, textvariable=self.var_fps, state=DISABLED)
        self.e_interval = Entry(
            frame, width=lwidth, textvariable=self.var_interval, state=DISABLED
        )
        # self.e_overhead    = Entry(frame, bd=0, width=ewidth, textvariable=self.var_overhead, state=DISABLED)

        Label(frame, width=lwidth, text='fps:').grid(row=1, column=0)
        self.e_fps.grid(row=1, column=1, sticky='we')
        Label(frame, width=lwidth, text='interval (ms):').grid(row=1, column=2)
        self.e_interval.grid(row=1, column=3, sticky='we')
        # Label(frame, width=lwidth, text="overhead (ms):").grid(row=1, column=4)
        # self.e_overhead.grid(row=1, column=5)

        frame.pack()

        frame = Frame(master)

        self.e_frametime = Spinbox(
            frame,
            width=ewidth,
            textvariable=self.var_frametime,
            from_=0.0,
            to=1.0,
            increment=0.01,
        )

        Label(frame, width=lwidth, text='exposure (s)').grid(row=1, column=0)
        self.e_frametime.grid(row=1, column=1)

        self.e_brightness = Spinbox(
            frame,
            width=ewidth,
            textvariable=self.var_brightness,
            from_=0.0,
            to=10.0,
            increment=0.1,
        )

        Label(frame, width=lwidth, text='Brightness').grid(row=1, column=2)
        self.e_brightness.grid(row=1, column=3)

        Label(frame, width=lwidth, text='DisplayRange').grid(row=1, column=4)
        self.e_display_range = Spinbox(
            frame,
            width=ewidth,
            textvariable=self.var_display_range,
            from_=1,
            to=self.display_range_default,
            increment=1000,
        )
        self.e_display_range.grid(row=1, column=5)

        frame.pack()

    def makepanel(self, master, resolution=(512, 512)):
        if self.panel is None:
            image = Image.fromarray(np.zeros(resolution))
            image = ImageTk.PhotoImage(image)
            self.panel = TkLabel(master, image=image, borderwidth=0)
            self.panel.image = image
            self.panel.pack(side='left', padx=10, pady=10)

    def update_resize_image(self, name, index, mode):
        # print name, index, mode
        try:
            self.resize_image = self.var_resize_image.get()
        except BaseException:
            pass

    def update_auto_contrast(self, name, index, mode):
        # print name, index, mode
        try:
            self.auto_contrast = self.var_auto_contrast.get()
        except BaseException:
            pass

    def update_frametime(self, name, index, mode):
        # print name, index, mode
        try:
            self.frametime = self.var_frametime.get() or self.frametime
        except BaseException:
            pass
        else:
            self.stream.update_frametime(self.frametime)

    def update_brightness(self, name, index, mode):
        # print name, index, mode
        try:
            self.brightness = self.var_brightness.get()
        except BaseException:
            pass

    def update_display_range(self, name, index, mode):
        try:
            val = self.var_display_range.get()
            self.display_range = max(1, val)
        except BaseException:
            pass

    def save_frame(self, frame: Optional[np.ndarray] = None, path: Optional[AnyPath] = None):
        """Save currently shown raw frame from the stream to a file in cwd."""
        frame = frame if frame is not None else self.processor.frame
        path = path or Path(self._saving_path_template().format('frame', 'tiff'))
        try:
            flatfield, _ = read_tiff(self.app.get_module('io').get_flatfield())
            frame = apply_flatfield_correction(frame, flatfield)
        except BaseException:
            frame = frame
        write_tiff(path, frame)
        print('Wrote frame:', path)

    def save_image(self, image: Optional[Image.Image] = None, path: Optional[AnyPath] = None):
        """Save currently shown, modified, & scaled image to a file in cwd."""
        image = image if image is not None else self.processor.image
        path = path or Path(self._saving_path_template().format('image', 'png'))
        image.save(path, format='PNG')
        print('Wrote image:', path)

    def _saving_path_template(self) -> str:
        try:
            drc = self.app.get_module('io').get_experiment_directory()
            drc.mkdir(exist_ok=True, parents=True)
        except (AttributeError, FileExistsError, PermissionError):
            drc = Path.cwd()
        timestamp = datetime.now().strftime('%H-%M-%S_%f')[:-3]
        return str(drc / f'{{}}_{timestamp}.{{}}')

    def close(self):
        self.stream.close()
        self.parent.quit()
        # for func in self._atexit_funcs:
        # func()

    def start_stream(self):
        self.stream.update_frametime(self.frametime)
        self.after(500, self.on_frame)

    def on_frame(self, event=None):
        """Get the newest image from `processor`, adapt to GUI and display."""
        if self.frame is not None:
            image = self.processor.image
            if self.resize_image:
                size = [2 * dim for dim in image.size]
                image = image.resize(size=size, resample=Resampling.NEAREST)
            image = ImageTk.PhotoImage(image=image)
            self.panel.configure(image=image)
            # keep a reference to avoid premature garbage collection
            self.panel.image = image
        self.update_frametimes()
        self.after(self.frame_delay, self.on_frame)

    def update_frametimes(self):
        self.current = time.perf_counter()
        delta = self.current - self.last

        if delta > self.update_frequency:
            interval = delta / self.nframes

            interval = (interval * 0.5) + (self.last_interval * 0.5)

            fps = 1.0 / interval
            # overhead = interval - self.stream.frametime

            self.var_fps.set(round(fps, 2))
            self.var_interval.set(round(interval * 1000, 2))
            # self.var_overhead.set(round(overhead*1000, 2))
            self.last = self.current
            self.nframes = 1

            self.last_interval = interval
        else:
            self.nframes += 1

    def on_click(self, event: Event) -> None:
        """Handle click events on the image via `self.click_service`"""
        if not self.click_dispatcher.active:
            return

        # Correct for window offset due to scrolling or not fitting on screen
        p = self.panel
        offset_x = (p.winfo_width() - p.image.width()) // 2
        offset_y = (p.winfo_height() - p.image.height()) // 2

        # Convert window coordinates to image coordinates
        array_shape = self.frame.shape
        x = round((event.x - offset_x) * array_shape[1] / p.image.width())
        y = round((event.y - offset_y) * array_shape[0] / p.image.height())
        self.click_dispatcher.handle_click(x=x, y=y, button=event.num)


module = BaseModule(
    name='stream', display_name='Stream', tk_frame=VideoStreamFrame, location='left'
)
commands = {}


def start_gui(stream):
    """Pass a camera stream object, and open a simple live-view window This is
    meant to be used in an interactive python shell."""
    root = Tk()
    vsframe = VideoStreamFrame(root, stream=stream)
    vsframe.pack(side='top', fill='both', expand=True)
    root.mainloop()
    root.destroy()


def ipy_embed(*args, **kwargs):
    """Embed an ipython terminal."""
    import IPython

    IPython.embed(*args, **kwargs)


if __name__ == '__main__':
    from instamatic import config
    from instamatic.camera import LiveVideoStream

    stream = LiveVideoStream(cam=config.camera.name)

    if False:
        threading.Thread(target=ipy_embed).start()
        start_gui()
    else:
        t = threading.Thread(target=start_gui, args=(stream,))
        t.start()

        import IPython

        IPython.embed()
