



class AcquireAtItems(object):
    """Class to automated acquisition at many stage locations.

    Parameters
    ----------
    ctrl: Instamatic.TEMController object
        Used to control the stage and TEM
    nav_items: list
        List of navigation items loaded from a `.nav` file.
    acquire: callable
        Main function to call, must take `ctrl` as an argument
    pre_acquire: callable
        This function is called before the first acquisition item is run.
    post_acquire: callable
        This function is run after the last acquisition item has run.
    backlash: bool
        Move the stage with backlash correction.

    Returns
    -------
    aai: `AcquireatItems`
        Returns instance of AcquireAtItems, run `aai.start()` to begin.
    """
    def __init__(self, ctrl,
                       nav_items: list, 
                       acquire=None, 
                       pre_acquire=None, 
                       post_acquire=None, 
                       backlash: bool=True):
        super(AcquireAtItems, self).__init__()
        
        self.nav_items = nav_items
        self.ctrl = ctrl

        if pre_acquire:
            self.pre_acquire = pre_acquire

        if post_acquire:
            self.post_acquire = post_acquire

        if acquire:
            self.acquire = acquire

        self.backlash = backlash

    def pre_acquire(self, ctrl):
        pass

    def post_acquire(self, ctrl):
        pass

    def acquire(self, ctrl):
        print("Acquirement function has not been set.")

    def move_to_item(self, item):
        x = item.stage_x * 1000  # um -> nm
        y = item.stage_y * 1000  # um -> nm

        if self.backlash:
            set_xy = self.ctrl.stageposition.set_xy_with_backlash_correction
        else:
            set_xy = self.ctrl.stageposition.set

        set_xy(x=x, y=y)

    def start(self):
        import time
        import msvcrt

        ctrl = self.ctrl
        nav_items = self.nav_items

        ntot = len(nav_items)

        print(f"\nAcquiring on {ntot} items.")
        print("Press <Q> to interrupt.\n")

        self.pre_acquire:

        t0 = t_last = time.perf_counter()
        eta = 999
        last_interval = interval = 1
        
        for i, item in enumerate(nav_items):
            ctrl.current_item = item
            ctrl.current_i = i
        
            print(f"{i}/{ntot} - `{item}` -> (ETA: {eta:.0f} min)")
            
            self.move_to_item(item)

            self.acquire(ctrl)
        
            # calculate remaining time
            t = time.perf_counter()
            interval = t - t_last
            last_interval = interval = (interval * 0.10) + (last_interval * 0.90)
            eta = ((ntot-i)*interval) / 60 # min
            t_last = t
        
            # Stop/interrupt acquisition
            if msvcrt.kbhit():
                key = msvcrt.getch().decode()
                if key == "q":
                    print("Acquisition was interrupted!")
                    break

        t1 = time.perf_counter()

        self.post_acquire(ctrl)

        dt = t1-t0
        print(f"Total time taken: {dt:.0f} s ({dt/i:.2f} s/item)")

