from instamatic.tools import relativistic_wavelength
import yaml
from instamatic import config
from pathlib import Path
import shutil


def get_tvips_calibs(ctrl, rng: list, mode: str, wavelength: float) -> dict:
    """Loop over magnification ranges and return calibrations from EMMENU"""

    if mode == "diff":
        print("Warning: Pixelsize can be a factor 10 off in diff mode (bug in EMMENU)")

    calib_range = {}

    BinX, BinY = ctrl.cam.getBinning()
    assert BinX == BinY, "Binnings differ in X and Y direction?! (X: {BinX} | Y: {BinY})"

    ctrl.mode(mode)

    for mag in rng:
        ctrl.magnification.set(mag)
        d = ctrl.cam.getCurrentCameraInfo()

        PixelSizeX = d["PixelSizeX"]
        PixelSizeY = d["PixelSizeY"]
        assert PixelSizeX == PixelSizeY, "Pixelsizes differ in X and Y direction?! (X: {PixelSizeX} | Y: {PixelSizeY})"

        if mode == "diff":
            pixelsize = np.sin(PixelSizeX / 1_000_000) / wavelength  #  µrad/px -> rad/px -> px/Å
        else:
            pixelsize = PixelSizeX

        calib_range[mode] = pixelsize

    return calib_range


def main():
    """
    This tool will help to set up the configuration files for `instamatic`
    It establishes a connection to the microscope and reads out the camera lengths
    and magnification ranges
    """

    print("\n 1: jeol\n 2: fei\n 3: simulate")

    q = int(input("\nWhich microscope can I connect to? [simulate] >> ") or 3)

    if q == 1:
        tem_name = "jeol"
    elif q == 2:
        tem_name = "fei"
    elif q == 3:
        tem_name = "simulate"
    else:
        raise ValueError(f"No microscope with index {q}")

    # print("\n 1: gatan (orius)\n 2: timepix\n 3: tvips (emmenu)")
    print("\n 0: None\n 3: tvips (emmenu)\n 4: simulate")

    q = int(input("\nWhich camera can I connect to? [None] >> ") or 0)

    if not q:
        cam_name = None
    elif q == 1:
        cam_name = "gatan"
    elif q == 2:
        cam_name = "timepix"
    elif q == 3:
        cam_name = "tvips"
    elif q == 4:
        cam_name = "simulate"
    else:
        raise ValueError(f"No camera with index {q}")

    drc = Path(__file__).parent
    default_configs = list(drc.glob("camera/*.yaml"))
    print("\n 0 - None")
    for i, default_config in enumerate(default_configs):
        print(f"{i+1: 2d} - {default_config.stem}")  # 1-indexed

    q = int(input("\nWhich camera type do you want to use (select closest one and modify if needed) [None] >> ") or 0)

    if not q:
        cam_config = None
    elif 0 < q < len(default_configs):
        cam_config = default_configs[q-1]  # 0-indexed
    else:
        raise ValueError(f"No config with index {q}")

    if tem_name == "simulate":
        ranges = {"mag1": [1, 2, 3], "diff": [10, 20, 30]}
        ht = 120000
    else:    
        from instamatic.TEMController import initialize
    
        ctrl = initialize(tem_name=tem_name, cam_name=cam_name)
        ranges = ctrl.magnification.get_ranges()
    
        ht = ctrl.HTValue.get()  # in V

    wavelength = relativistic_wavelength(ht)

    tem_config = {}
    tem_config["name"] = tem_name
    tem_config["wavelength"] = wavelength

    for mode, rng in ranges.items():
        tem_config["range_"+mode] = rng

    calib_config = {}
    calib_config["name"] = tem_name

    for mode, rng in ranges.items():
        if cam_name == "tvips":
            pixelsizes = get_tvips_calibs(ctrl=ctrl, rng=rng, mode=mode, wavelength=wavelength)
        else:
            pixelsizes = {r: 1.0 for r in rng}
        calib_config["pixelsize_"+mode] = pixelsizes

    tem_config_fn = f"{tem_name}_tem.yaml"
    calib_config_fn = f"{tem_name}_calib.yaml"
    if cam_config:
        cam_config_fn = f"{cam_name}_cam.yaml"
        shutil.copyfile(cam_config, cam_config_fn)

    yaml.dump(tem_config, open(tem_config_fn, "w"), sort_keys=False)
    yaml.dump(calib_config, open(calib_config_fn, "w"), sort_keys=False)
    
    print()
    print(f"Wrote files config files:")
    print(f"    Copy {tem_config_fn} -> `{config.config_drc / tem_config_fn}`")
    print(f"    Copy {calib_config_fn} -> `{config.config_drc / calib_config_fn}`")
    if cam_config:
        print(f"    Copy {cam_config_fn} -> `{config.config_drc / cam_config_fn}`")
    print()
    print(f"In `{config.config_drc / 'global.yaml'}`:")
    print(f"    microscope: {tem_name}_tem")
    print(f"    calibration: {tem_name}_calib")
    if cam_config:
        print(f"    camera: {cam_name}_cam")
    print()
    print(f"Todo: Check and update the pixelsizes in `{calib_config_fn}`")
    print( "    In real space, pixelsize in nm")
    print( "    In reciprocal space, pixelsize in px/Angstrom")


if __name__ == '__main__':
    main()
