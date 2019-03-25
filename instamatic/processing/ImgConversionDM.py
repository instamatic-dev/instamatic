from .ImgConversion import *


class ImgConversionDM(ImgConversion):
    """This class is for converting data collected with the insteaDMatic DM-script
    Files can be generated for REDp, DIALS, XDS, and PETS.

    The image buffer is passed as a list of tuples, where each tuple contains the
    index (int), image data (2D numpy array), metadata/header (dict).
    The buffer index must start at 1.
    """

    def __init__(self, 
                 buffer: list,                   # image buffer, list of (index [int], image data [2D numpy array], header [dict])
                 osc_angle: float,               # degrees, oscillation angle of the rotation
                 start_angle: float,             # degrees, start angle of the rotation
                 end_angle: float,               # degrees, end angle of the rotation
                 rotation_axis: float,           # radians, specifies the position of the rotation axis
                 acquisition_time: float,        # seconds, acquisition time (exposure time + overhead)
                 flatfield: str='flatfield.tiff',
                 pixelsize: float=None,          # p/Angstrom, size of the pixels (overrides camera_length)
                 physical_pixelsize: float=None, # mm, physical size of the pixels (overrides camera length)
                 wavelength: float=None,         # Angstrom, relativistic wavelength of the electron beam
                 ):
        if flatfield is not None:
            flatfield, h = read_tiff(flatfield)
        self.flatfield = flatfield

        self.headers = {}
        self.data = {}

        self.smv_subdrc = "data"

        while len(buffer) != 0:
            i, img, h = buffer.pop(0)

            self.headers[i] = h

            if self.flatfield is not None:
                self.data[i] = apply_flatfield_correction(img, self.flatfield)
            else:
                self.data[i] = img

        self.observed_range = set(self.data.keys())
        self.complete_range = set(range(min(self.observed_range), max(self.observed_range) + 1))
        self.missing_range = self.observed_range ^ self.complete_range

        self.data_shape = img.shape

        self.pixelsize = pixelsize
        self.physical_pixelsize = physical_pixelsize
        self.wavelength = wavelength

        self.mean_beam_center, self.beam_center_std = self.get_beam_centers()
        self.distance = (1/self.wavelength) * (self.physical_pixelsize / self.pixelsize)
        self.osc_angle = osc_angle
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.rotation_axis = rotation_axis
        
        self.acquisition_time = acquisition_time
        self.rotation_speed = get_calibrated_rotation_speed(osc_angle / self.acquisition_time) 

        logger.debug("Primary beam at: {}".format(self.mean_beam_center))

    def write_smv(self, path: str, i: int) -> str:
        """Write the image+header with sequence number `i` to the directory `path` in SMV format.
        Returns the path to the written image."""
        img = self.data[i]
        h = self.headers[i]

        img = np.ushort(img)
        shape_x, shape_y = img.shape
        
        phi = self.start_angle + self.osc_angle * (i-1)

        # TODO: Dials reads the beam_center from the first image and uses that for the whole range
        # For now, use the average beam center and consider it stationary, remove this line later
        mean_beam_center = self.mean_beam_center
        
        header = collections.OrderedDict()
        header['HEADER_BYTES'] = 512
        header['DIM'] = 2
        header['BYTE_ORDER'] = "little_endian"
        header['TYPE'] = "unsigned_short"
        header['SIZE1'] = shape_x
        header['SIZE2'] = shape_y
        header['PIXEL_SIZE'] = self.physical_pixelsize
        header['BIN'] = "1x1"
        header['BIN_TYPE'] = "HW"
        header['ADC'] = "fast"
        header['CREV'] = 1
        header['BEAMLINE'] = "DigitalMicrograph"   # special ID for DIALS
        header['DETECTOR_SN'] = 901         # special ID for DIALS
        header['DATE'] = "0" # str(datetime.fromtimestamp(h["ImageGetTime"]))
        header['TIME'] = str(h["ImageExposureTime"])
        header['DISTANCE'] = "{:.4f}".format(self.distance)
        header['TWOTHETA'] = 0.00
        header['PHI'] = "{:.4f}".format(phi)
        header['OSC_START'] = "{:.4f}".format(phi)
        header['OSC_RANGE'] = "{:.4f}".format(self.osc_angle)
        header['WAVELENGTH'] = "{:.4f}".format(self.wavelength)
        # reverse XY coordinates for XDS
        header['BEAM_CENTER_X'] = "{:.4f}".format(mean_beam_center[1])
        header['BEAM_CENTER_Y'] = "{:.4f}".format(mean_beam_center[0])
        header['DENZO_X_BEAM'] = "{:.4f}".format((mean_beam_center[0]*self.physical_pixelsize))
        header['DENZO_Y_BEAM'] = "{:.4f}".format((mean_beam_center[1]*self.physical_pixelsize))
        fn = path / f"{i:05d}.img"
        write_adsc(fn, img, header=header)
        return fn
        
    def write_xds_inp(self, path: str) -> None:
        """Write XDS.INP input file for XDS in directory `path`"""
        from .XDS_templateDM import XDS_template

        path.mkdir(exist_ok=True)

        nframes = max(self.complete_range)

        invert_rotation_axis = self.start_angle > self.end_angle
        rot_x, rot_y, rot_z = rotation_axis_to_xyz(self.rotation_axis, invert=invert_rotation_axis)

        shape_x, shape_y = self.data_shape

        if self.missing_range:
            exclude = "\n".join(["EXCLUDE_DATA_RANGE={} {}".format(i, j) for i, j in find_subranges(self.missing_range)])
        else:
            exclude = "!EXCLUDE_DATA_RANGE="

        s = XDS_template.format(
            date=str(time.ctime()),
            data_drc=self.smv_subdrc,
            data_begin=1,
            data_end=nframes,
            exclude=exclude,
            starting_angle=self.start_angle,
            wavelength=self.wavelength,
            # reverse XY coordinates for XDS
            origin_x=self.mean_beam_center[1],
            origin_y=self.mean_beam_center[0],
            NX=shape_y,
            NY=shape_x,
            sign="+",
            detector_distance=self.distance,
            QX=self.physical_pixelsize,
            QY=self.physical_pixelsize,
            osc_angle=self.osc_angle,
            rot_x=rot_x,
            rot_y=rot_y,
            rot_z=rot_z
            )
       
        with open(path / 'XDS.INP','w') as f:
            print(s, file=f)
        
        logger.info("XDS INP file created.")

    def write_beam_centers(self, path: str) -> None:
        """Write list of beam centers to file `beam_centers.txt` in `path`"""
        centers = np.zeros((max(self.observed_range), 2), dtype=np.float)
        for i, h in self.headers.items():
            centers[i-1] = h["beam_center"]
        for i in self.missing_range:
            centers[i-1] = [np.NaN, np.NaN]

        np.savetxt(path / "beam_centers.txt", centers, fmt="%10.4f")

    def write_pets_inp(self, path: str, tiff_path: str="tiff") -> None:
        """Write PETS input file `pets.pts` in directory `path`"""
        if self.start_angle > self.end_angle:
            sign = -1
        else:
            sign = 1

        with open(path / "pets.pts", "w") as f:
            date = str(time.ctime())
            print("# PETS input file for Rotation Electron Diffraction generated by `instamatic`", file=f)
            print(f"# {date}", file=f)
            print("# For definitions of input parameters, see:", file=f) 
            print("# http://pets.fzu.cz/ ", file=f)
            print("", file=f)
            print(f"lambda {self.wavelength}", file=f)
            print(f"Aperpixel {self.pixelsize}", file=f)
            print(f"phi 0.0", file=f)
            print(f"omega {np.degrees(self.rotation_axis + np.pi*2)}", file=f)
            print(f"bin 1", file=f)
            print(f"reflectionsize 20", file=f)
            print(f"noiseparameters 3.5 38", file=f)
            print("", file=f)
            # print("reconstructions", file=f)
            # print("endreconstructions", file=f)
            # print("", file=f)
            # print("distortions", file=f)
            # print("enddistortions", file=f)
            # print("", file=f)
            print("imagelist", file=f)
            for i in self.observed_range:
                fn = "{:05d}.tiff".format(i)
                angle = self.start_angle+sign*self.osc_angle*i
                print(f"{tiff_path}/{fn} {angle:10.4f} 0.00", file=f)
            print("endimagelist", file=f)
    
