

class AcquireAtItems(object):
    """Class to automated acquisition at many stage locations.

    Parameters
    ----------
    ctrl: Instamatic.TEMController object
        Used to control the stage and TEM
    nav_items: list
        List of (x, y) / (x, y, z) coordinates, or
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
            print("Pre-acquire: OK")
            self.pre_acquire = pre_acquire

        if acquire:
            print("Acquire: OK")
            self.acquire = acquire

        if post_acquire:
            print("Post-acquire: OK")
            self.post_acquire = post_acquire

        self.backlash = backlash

    def pre_acquire(self, ctrl):
        """Function called after the last NavItem"""
        pass

    def post_acquire(self, ctrl):
        """Function called before the first NavItem"""
        pass

    def acquire(self, ctrl):
        """Function to call at each stage position"""
        print("Acquirement function has not been set.")

    def move_to_item(self, item):
        """Move the stage to the stage coordinates given by the NavItem"""
        try:
            x = item.stage_x * 1000  # um -> nm
            y = item.stage_y * 1000  # um -> nm
            z = item.stage_z * 1000  # um -> nm
        except AttributeError:
            if len(item) == 2:
                x, y = item
                z = None
            elif len(item) == 3:
                x, y, z = item
            else:
                raise IndexError(f"Coordinate must have 2 (x, y) or 3 (x, y, z) elements: {item}")

        if z != None:
            self.ctrl.stage.set(z=z)

        if self.backlash:
            set_xy = self.ctrl.stage.set_xy_with_backlash_correction
        else:
            set_xy = self.ctrl.stage.set

        set_xy(x=x, y=y)

    def start(self):
        """Start serial acquisition protocol"""
        import time
        import msvcrt

        ctrl = self.ctrl
        nav_items = self.nav_items

        ntot = len(nav_items)

        print(f"\nAcquiring on {ntot} items.")
        print("Press <Q> to interrupt.\n")

        self.pre_acquire(ctrl)

        t0 = t_last = time.perf_counter()
        eta = 0
        last_interval = interval = 1
        
        for i, item in enumerate(nav_items):
            ctrl.current_item = item
            ctrl.current_i = i
        
            print(f"{i}/{ntot} - `{item}` -> (ETA: {eta:.0f} min)")
            
            self.move_to_item(item)

            try:
                self.acquire(ctrl)
            except InterruptedError:
                print(f"\nAcquisition was interrupted during item `{item}`!")
                break

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
                    print(f"\nAcquisition was interrupted after item `{item}`!")
                    break

        t1 = time.perf_counter()

        self.post_acquire(ctrl)

        dt = t1-t0
        n_items = i+1
        print(f"Total time taken: {dt:.0f} s for {n_items} items ({dt/n_items:.2f} s/item)")
        print("\nAll done!")
