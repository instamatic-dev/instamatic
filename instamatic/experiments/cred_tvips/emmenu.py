import pyautogui as pg
import pygetwindow as pw
from pathlib import Path


class EMMenuError(Exception):
    pass


class EMMenuWrapper(object):
    """Small wrapper the EMMenu gui for automating data collection"""
    def __init__(self):
        super(EMMenuWrapper, self).__init__()
        curdir = Path(__file__).parent

        path_start_liveview_button = curdir / "start_liveview.png"
        path_start_record_button   = curdir / "start_record.png"
        path_stop_liveview_button1 = curdir / "stop_liveview1.png"
        path_stop_liveview_button2 = curdir / "stop_liveview2.png"

        pg.alert(text="does this work", title="Error encountered?", button="sup")

        windows = pw.getWindowsWithTitle("EMMENU")
        if len(windows) == 0:
            raise EMMenuError("Could not find EMMENU, is it running?")
        if len(windows > 1):
            raise EMMenuError("Found more than one instance of EMMENU -> ???")

        self.win_emmenu = windows[0]
        self.activate()

        self.locate_buttons()

        self.previous_window = None

    def locate_buttons(self):
        """Locate the buttons to start/stop recording/live view"""
        record_button_pos = pg.locateCenterOnScreen(path_start_record_button)
        if not record_button_pos:
            raise EMMenuError("Could not locate live view button")
        self.record_button_pos = record_button_pos
        
        # attempt 1, liveview is running
        liveview_button_pos = pg.locateCenterOnScreen(path_stop_liveview_button1)
        if not liveview_button_pos:
            # attempt 2, liveview is not running
            liveview_button_pos = pg.locateCenterOnScreen(path_start_liveview_button)
            if not liveview_button_pos:
                # attempt 3, liveview is running, but deselected
                liveview_button_pos = pg.locateCenterOnScreen(path_stop_liveview_button2)
                if not liveview_button_pos:
                    raise EMMenuError("Could not locate record button")
        self.liveview_button_pos = liveview_button_pos

    def activate(self):
        if not self.win_emmenu.isActive:
            self.win_previous = pygetwindow.getActiveWindow()
        self.win_emmenu.activate()
        self.win_emmenu.maximize()

    def activate_previous(self):
        if self.win_previous:
            self.win_previous.activate()

    def press_record(self):
        self.activate()
        pg.moveTo(self.record_button_pos)
        pg.click()

    def press_liveview(self):
        self.activate()
        pg.moveTo(self.liveview_button_pos)
        pg.click()
