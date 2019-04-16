import pyautogui as pg
import pygetwindow as pw
from instamatic.utils.singleton import Singleton
from pathlib import Path
from instamatic import config
from contextlib import contextmanager


class EMMenuError(Exception):
    pass


class EMMenuWrapper(object):
    """Small wrapper the EMMenu gui for automating data collection"""
    instance = None

    def __init__(self, name="emmenu"):
        super(EMMenuWrapper, self).__init__()

        self.name = name
        self._switch_back = True

        self.load_defaults()

        curdir = Path(__file__).parent

        self._path_start_liveview_button = str(curdir / "emmenu" / "start_liveview.png")
        self._path_start_record_button   = str(curdir / "emmenu" / "start_record.png")
        self._path_stop_liveview_button1 = str(curdir / "emmenu" / "stop_liveview1.png")
        self._path_stop_liveview_button2 = str(curdir / "emmenu" / "stop_liveview2.png")
        self._path_acquire_button        = str(curdir / "emmenu" / "acquire.png")

        self.win_previous = None
        windows = pw.getWindowsWithTitle("EMMENU4")

        if len(windows) == 0:
            raise EMMenuError("Could not find EMMENU, is it running?")
        if len(windows) > 1:
            for title in pw.getAllTitles():
                if title:
                    print(title)
            raise EMMenuError("Found more than one instance of EMMENU -> ???")

        self.win_emmenu = windows[0]
        
        self.locate_buttons()

    def load_defaults(self):
        if self.name != config.cfg.camera:
            config.load(camera_name=self.name)

        self.__dict__.update(config.camera.d)

        self.streamable = False

    def locate_buttons(self):
        """Locate the buttons to start/stop recording/live view"""
        self.activate()

        screenshot = pg.screenshot()

        # record_button_pos = (1071, 56, 18, 18)
        # liveview_button_pos = (1629, 238, 42, 18)
        # acquire_button_pos = (1628, 143, 44, 20)

        record_button_pos = pg.locate(self._path_start_record_button, screenshot, grayscale=True)
        if not record_button_pos:
            raise EMMenuError("Could not locate record view button")
        self.record_button_region = record_button_pos
        self.record_button_pos = pg.center(record_button_pos)
        
        # attempt 1, liveview is running
        liveview_button_pos = pg.locate(self._path_stop_liveview_button1, screenshot, grayscale=True)
        if not liveview_button_pos:
            # attempt 2, liveview is not running
            liveview_button_pos = pg.locate(self._path_start_liveview_button, screenshot, grayscale=True)
            if not liveview_button_pos:
                # attempt 3, liveview is running, but deselected
                liveview_button_pos = pg.locate(self._path_stop_liveview_button2, screenshot, grayscale=True)
                if not liveview_button_pos:
                    raise EMMenuError("Could not locate live view button")
        
        self.liveview_button_region = liveview_button_pos
        self.liveview_button_pos = pg.center(liveview_button_pos)

        acquire_button_pos = pg.locate(self._path_acquire_button, screenshot, grayscale=True)
        if not acquire_button_pos:
            raise EMMenuError("Could not locate record view button")
        self.acquire_button_region = acquire_button_pos
        self.acquire_button_pos = pg.center(acquire_button_pos)

        screenshot.close()

        print(f"Record button position: {self.record_button_pos} ({self.record_button_region})")
        print(f"Liveview button position: {self.liveview_button_pos} ({self.liveview_button_region})")
        print(f"Acquire button position: {self.acquire_button_pos} ({self.acquire_button_region})")

        self.activate_previous()

    def getImage(self, **kwargs):
        """Hi-jack `getImage` to display data collection warning."""
        raise IOError(f"{self.__class__.__name__} does not support `getImage`. Use `ctrl.cam.acquire` or `ctrl.cam.record` instead. The images will be stored in the EMMENU buffer.")

    def acquire(self):
        """
        Collect image on the camera using the currently selected camera in EMMENU. 
        The image is stored in the EMMENU buffer.
        """
        self._press(self.acquire_button_pos)

    def start_record(self):
        """Start recording the current live view of the currently selected camera. The data are saved in the EMMENU buffer."""
        self.toggle_record() 

    def stop_record(self):
        """Stop the recording."""
        self.toggle_liveview()

    @property
    def live_view_is_running(self):
        """Return `True` if the live view is running"""
        self.activate()

        region = self.liveview_button_region

        if pg.locateOnScreen(self._path_stop_liveview_button1, grayscale=True, region=region):
            ret = True
        elif pg.locateOnScreen(self._path_stop_liveview_button2, grayscale=True, region=region):
            ret = True
        else:
            ret = False

        self.activate_previous()
        
        return ret

    @property
    def record_is_running(self):
        """Return `True` if the live view is running"""
        self.activate()

        region = self.record_button_region

        if pg.locateOnScreen(self._path_start_record_button, grayscale=True, region=region):
            ret = True
        else:
            ret = False

        self.activate_previous()
        
        return ret

    @property
    def is_active(self):
        """Return `True` if EMMENU is the active window"""
        return self.win_emmenu.isActive

    def activate(self):
        """Active the EMMENU4 window"""
        if not self.is_active:
            self.win_previous = pw.getActiveWindow()
        self.win_emmenu.activate()
        self.win_emmenu.maximize()

    def activate_previous(self):
        """Go back to the previous active window after `self.activate` has been used"""
        if self.win_previous:
            self.win_previous.activate()

    def _press(self, button_loc):
        """Toggle the liveview button, and switch back to the currently active window"""
        switch_back = False
        current_loc = pg.position()
        if not self.is_active:
            self.activate()
            switch_back = True
        pg.moveTo(button_loc)
        pg.click()
        pg.moveTo(current_loc)
        if switch_back:
            self.activate_previous()

    def toggle_record(self):
        """Toggle the record button, and switch back to the currently active window"""
        self._press(self.record_button_pos)

    def stop_record(self):
        """Stop recording"""
        with self.keep_in_focus:
            if self.record_is_running:
                self._press(self.record_button_pos)

    def start_record(self):
        """Start recording"""
        with self.keep_in_focus:
            if not self.record_is_running:
                self._press(self.record_button_pos)
            else:
                print("Recording is already running")

    def toggle_liveview(self):
        """Toggle the liveview button, and switch back to the currently active window"""
        self._press(self.liveview_button_pos)

    def stop_liveview(self):
        """Stop liveview"""
        with self.keep_in_focus:
            if self.liveview_is_running:
                self._press(self.liveview_button_pos)

    def start_liveview(self):
        """Start liveview"""
        with self.keep_in_focus:
            if not self.liveview_is_running:
                self._press(self.liveview_button_pos)
            else:
                print("Recording is already running")

    @contextmanager
    def keep_in_focus(self):
        """Keep the EMMENU window in focus while executing a few clicks in a row to prevent windows flashing"""
        was_active = self.is_active
        self._switch_back = False
        yield
        self._switch_back = True
        if not was_active:
            self.activate_previous()
