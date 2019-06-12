from instamatic.tools import relativistic_wavelength
import yaml
from instamatic import config


def main():
    """
    This tool will help to set up the configuration files for `instamatic`
    It establishes a connection to the microscope and reads out the camera lengths
    and magnification ranges
    """

    print("\n 1: jeol\n 2: fei\n 3: simulate\n")

    q = int(input("Which microscope should I connect to? >> "))

    if q == 1:
        tem_name = "jeol"
    elif q == 2:
        tem_name = "fei"
    elif q == 3:
        tem_name = "simulate"
    else:
        raise ValueError(f"No microscope with index {q}")

    # print("\n 1: gatan (orius)\n 2: timepix\n 3: tvips (emmenu)")
    # print("\n 4: simulate\n 5: skip\n")

    # q = int(input("Which camera should I configure? >> "))

    # if q == 1:
    #     cam_name = "gatan"
    # elif q == 2:
    #     cam_name = "timepix"
    # elif q == 3:
    #     cam_name = "tvips"
    # elif q == 4:
    #     cam_name = "simulate"
    # elif q == 5:
    #     cam_name = None
    # else:
    #     raise ValueError(f"No camera with index {q}")

    if tem_name == "simulate":
        ranges = {"mag1": [1, 2, 3], "diff": [10, 20, 30]}
        ht = 120000
    else:    
        from instamatic.TEMController import initialize
    
        ctrl = initialize(tem_name=tem_name, cam_name=None)
        ranges = ctrl.magnification.get_ranges()
    
        ht = ctrl.HTValue.get()  # in V

    wavelength = relativistic_wavelength(ht)

    tem_config = {}
    tem_config["name"] = tem_name
    tem_config["wavelength"] = wavelength

    for k, v in ranges.items():
        tem_config["range_"+k] = v

    calib_config = {}
    calib_config["name"] = tem_name

    for k, r in ranges.items():
        pixelsizes = {val: 1.0 for val in r}
        calib_config["pixelsize_"+k] = pixelsizes

    tem_config_fn = f"{tem_name}_tem.yaml"
    calib_config_fn = f"{tem_name}_calib.yaml"
    # cam_config_fn = f"{cam_name}_cam.yaml"

    yaml.dump(tem_config, open(tem_config_fn, "w"), sort_keys=False)
    yaml.dump(calib_config, open(calib_config_fn, "w"), sort_keys=False)
    # yaml.dump(cam_config, open(cam_config_fn, "w"), sort_keys=False)
    
    print()
    print(f"Wrote files {tem_config_fn} and {calib_config_fn}")
    print(f"    Copy {tem_config_fn} -> `{config.config_drc / tem_config_fn}`")
    print(f"    Copy {calib_config_fn} -> `{config.config_drc / calib_config_fn}`")
    # print(f"    Copy {cam_config_fn} -> `{config.config_drc / cam_config_fn}`")
    print()
    print(f"In `{config.config_drc / 'global.yaml'}`:")
    print(f"    microscope: {tem_name}_tem")
    print(f"    calibration: {tem_name}_calib")
    # print(f"    camera: {camera_name}_cam")
    print()
    print(f"Todo: Update the pixelsizes in `{calib_config_fn}`")
    print( "      In real space, pixelsize in nm")
    print( "      In reciprocal space, pixelsize in px/Angstrom")


if __name__ == '__main__':
    main()
