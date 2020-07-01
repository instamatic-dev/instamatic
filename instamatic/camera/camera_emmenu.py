import atexit
import logging
import time
from pathlib import Path

import comtypes.client
import numpy as np

from instamatic import config
logger = logging.getLogger(__name__)


type_dict = {
    1: 'GetDataByte',
    2: 'GetDataUShort',
    3: 'GetDataShort',
    4: 'GetDataLong',
    5: 'GetDataFloat',
    6: 'GetDataDouble',
    7: 'GetDataComplex',
    8: 'IMG_STRING',  # no method on EMImage
    9: 'GetDataBinary',
    10: 'GetDataRGB8',
    11: 'GetDataRGB16',
    12: 'IMG_EMVECTOR',  # no method on EMImage
}


def EMVector2dict(vec):
    """Convert EMVector object to a Python dictionary."""
    d = {}
    for k in dir(vec):
        if k.startswith('_'):
            continue
        v = getattr(vec, k)
        if isinstance(v, int):
            d[k] = v
        elif isinstance(v, float):
            d[k] = v
        elif isinstance(v, str):
            d[k] = v
        elif isinstance(v, comtypes.Array):
            d[k] = list(v)
        else:
            print(k, v, type(v))

    return d


class CameraEMMENU:
    """Software interface for the EMMENU program.

    Communicates with EMMENU over the COM interface defined by TVIPS

    drc_name : str
        Set the default folder to store data in
    name : str
        Name of the interface
    """

    def __init__(
        self,
        drc_name: str = 'Diffraction',
        name: str = 'emmenu',
    ):
        """Initialize camera module."""
        super().__init__()

        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            comtypes.CoInitialize()

        self.name = name

        self._obj = comtypes.client.CreateObject('EMMENU4.EMMENUApplication.1', comtypes.CLSCTX_ALL)

        self._recording = False

        # get first camera
        self._cam = self._obj.TEMCameras.Item(1)

        # hi-jack first viewport
        self._vp = self._obj.Viewports.Item(1)
        self._vp.SetCaption('Instamatic viewport')  # 2.5 ms
        self._vp.FlapState = 2  # pull out the flap, because we can :-) [0, 1, 2]

        self._obj.Option('ClearBufferOnDeleteImage')   # `Delete` -> Clear buffer (preferable)
        # other choices: DeleteBufferOnDeleteImage / Default

        # Image manager for managing image buffers (left panel)
        self._immgr = self._obj.ImageManager

        # for writing tiff files
        self._emf = self._obj.EMFile

        # stores all pointers to image data
        self._emi = self._obj.EMImages

        # set up instamatic data directory
        self.top_drc_index = self._immgr.TopDirectory
        self.top_drc_name = self._immgr.DirectoryName(self.top_drc_index)

        # check if exists
        if not self._immgr.DirectoryExist(self.top_drc_index, drc_name):
            if self.getEMMenuVersion().startswith('4.'):
                self._immgr.CreateNewSubDirectory(self.top_drc_index, drc_name, 2, 2)
            else:
                # creating new subdirectories is bugged in EMMENU 5.0.9.0/5.0.10.0
                # No work-around -> raise exception for now until it is fixed
                raise ValueError(f'Directory `{drc_name}` does not exist in the EMMENU Image manager.')

        self.drc_name = drc_name
        self.drc_index = self._immgr.DirectoryHandleFromName(drc_name)

        self._vp.DirectoryHandle = self.drc_index  # set current directory

        self.load_defaults()

        msg = f'Camera `{self.getCameraName()}` ({self.name}) initialized'
        # print(msg)
        logger.info(msg)

        atexit.register(self.releaseConnection)

    def load_defaults(self) -> None:
        if self.name != config.settings.camera:
            config.load_camera_config(camera_name=self.name)

        self.__dict__.update(config.camera.mapping)

        self.streamable = False

    def listConfigs(self) -> list:
        """List the configs from the Configuration Manager."""
        print(f'Configurations for camera {self.name}')
        current = self._vp.Configuration

        lst = []

        for i, cfg in enumerate(self._obj.CameraConfigurations):
            is_selected = (current == cfg.Name)
            end = ' (selected)' if is_selected else ''
            print(f'{i+1:2d} - {cfg.Name}{end}')
            lst.append(cfg.Name)

        return lst

    def getCurrentConfigName(self) -> str:
        """Return the name of the currently selected configuration in
        EMMENU."""
        cfg = self.getCurrentConfig(as_dict=False)
        return cfg.Name

    def getCurrentConfig(self, as_dict: bool = True) -> dict:
        """Get selected config object currently associated with the
        viewport."""
        vp_cfg_name = self._vp.Configuration
        count = self._obj.CameraConfigurations.Count
        for j in range(1, count + 1):
            cfg = self._obj.CameraConfigurations.Item(j)
            if cfg.Name == vp_cfg_name:
                break

        if as_dict:
            d = {}
            d['Name'] = cfg.Name  # str
            d['CCDOffsetX'] = cfg.CCDOffsetX  # int
            d['CCDOffsetY'] = cfg.CCDOffsetY  # int
            d['DimensionX'] = cfg.DimensionX  # int
            d['DimensionY'] = cfg.DimensionY  # int
            d['BinningX'] = cfg.BinningX  # int
            d['BinningY'] = cfg.BinningY  # int
            d['CameraType'] = cfg.CameraType  # str
            d['GainValue'] = cfg.GainValue  # float
            d['SpeedValue'] = cfg.SpeedValue  # int
            d['FlatMode'] = cfg.FlatMode  # int
            d['FlatModeStr'] = ('Uncorrected', 'Dark subtracted', None, 'Gain corrected')[cfg.FlatMode]  # str, 2 undefined
            d['PreExposureTime'] = cfg.PreExposureTime  # int
            d['UsePreExposure'] = bool(cfg.UsePreExposure)
            d['ReadoutMode'] = cfg.ReadoutMode  # int
            d['ReadoutModeStr'] = (None, 'Normal', 'Frame transfer', 'Rolling shutter')[cfg.ReadoutMode]  # str, 0 undefined
            d['UseRollingAverage'] = bool(cfg.UseRollingAverage)
            d['RollingAverageValue'] = cfg.RollingAverageValue  # int
            d['UseRollingShutter'] = bool(cfg.UseRollingShutter)
            d['UseScriptPreExposure'] = bool(cfg.UseScriptPreExposure)
            d['UseScriptPostExposure'] = bool(cfg.UseScriptPostExposure)
            d['UseScriptPreContinuous'] = bool(cfg.UseScriptPreContinuous)
            d['UseScriptPostContinuous'] = bool(cfg.UseScriptPostContinuous)
            d['ScriptPathPostExposure'] = cfg.ScriptPathPostExposure  # str
            d['ScriptPathPreContinuous'] = cfg.ScriptPathPreContinuous  # str
            d['ScriptPathPostContinuous'] = cfg.ScriptPathPostContinuous  # str
            d['ScriptPathBeforeSeries'] = cfg.ScriptPathBeforeSeries  # str
            d['ScriptPathWithinSeries'] = cfg.ScriptPathWithinSeries  # str
            d['ScriptPathAfterSeries'] = cfg.ScriptPathAfterSeries  # str
            d['SCXAmplifier'] = cfg.SCXAmplifier  # int
            d['SCXAmplifierStr'] = ('Unknown', 'Low noise', 'High capacity')[cfg.SCXAmplifier]  # str
            d['CenterOnChip'] = bool(cfg.CenterOnChip)
            d['SeriesType'] = cfg.SeriesType  # int
            d['SeriesTypeStr'] = ('Single image', 'Delay series', 'Script series')[cfg.SeriesType]  # str
            d['SeriesNumberOfImages'] = cfg.SeriesNumberOfImages
            d['SeriesDelay'] = cfg.SeriesDelay  # int
            d['SeriesAlignImages'] = bool(cfg.SeriesAlignImages)
            d['SeriesIntegrateImages'] = bool(cfg.SeriesIntegrateImages)
            d['SeriesAverageImages'] = bool(cfg.SeriesAverageImages)
            d['SeriesDiscardIndividualImages'] = bool(cfg.SeriesDiscardIndividualImages)
            d['UseScriptBeforeSeries'] = bool(cfg.UseScriptBeforeSeries)
            d['UseScriptWithinSeries'] = bool(cfg.UseScriptWithinSeries)
            d['UseScriptAfterSeries'] = bool(cfg.UseScriptAfterSeries)
            d['ShutterMode'] = cfg.ShutterMode  # int
            d['ShutterModeStr'] = ('None', 'SH', 'BB', 'SH/BB', 'Dark/SH', 'Dark/BB', 'Dark/SH/BB')[cfg.ShutterMode]  # str
            return d
        else:
            return cfg

    def selectConfig(self) -> None:
        """Select config by name."""
        cfgs = self.listConfigs()
        if config not in cfgs:
            raise ValueError(f'No such config: {config} -> must be one of {cfgs}')

        raise NotImplementedError

    def getCurrentCameraInfo(self) -> dict:
        """Gets the current camera object."""
        cam = self._cam

        d = {}
        d['RealSizeX'] = cam.RealSizeX  # int
        d['RealSizeY'] = cam.RealSizeY  # int
        d['MaximumSizeX'] = cam.MaximumSizeX  # int
        d['MaximumSizeY'] = cam.MaximumSizeY  # int
        d['NumberOfGains'] = cam.NumberOfGains  # int
        d['GainValues'] = [cam.GainValue(val) for val in range(cam.NumberOfGains + 1)]
        d['NumberOfSpeeds'] = cam.NumberOfSpeeds  # int
        d['SpeedValues'] = [cam.SpeedValue(val) for val in range(cam.NumberOfSpeeds + 1)]
        d['PixelSizeX'] = cam.PixelSizeX  # int
        d['PixelSizeY'] = cam.PixelSizeY  # int
        d['Dynamic'] = cam.Dynamic  # int
        d['PostMag'] = cam.PostMag  # float
        d['CamCGroup'] = cam.CamCGroup  # int
        return d

    def getCameraType(self) -> str:
        """Get the name of the camera currently in use."""
        cfg = self.getCurrentConfig(as_dict=False)
        return cfg.CameraType

    def getEMMenuVersion(self) -> str:
        """Get the version number of EMMENU."""
        return self._obj.EMMENUVersion

    def lock(self) -> None:
        """Lockdown interactions with emmenu, must call `self.unlock` to
        unlock.

        If EMMenu is locked, no mouse or keyboard input will be accepted
        by the interface. The script calling this function is
        responsible for unlocking EMMenu.
        """
        self._obj.EnableMainframe(1)

    def unlock(self) -> None:
        """Unlock emmenu after it has been locked down with `self.lock`"""
        self._obj.EnableMainframe(0)

    def listDirectories(self) -> dict:
        """List subdirectories of the top directory."""
        top_j = self._immgr.TopDirectory
        top_name = self._immgr.FullDirectoryName(top_j)
        print(f'{top_name} ({top_j})')

        drc_j = self._immgr.SubDirectory(top_j)

        d = {}

        while drc_j:
            drc_name = self._immgr.FullDirectoryName(drc_j)
            print(f'{drc_j} - {drc_name} ')

            d[drc_j] = drc_name

            drc_j = self._immgr.NextDirectory(drc_j)  # get next

        return d

    def getEMVectorByIndex(self, img_index: int, drc_index: int = None) -> dict:
        """Returns the EMVector by index as a python dictionary."""
        p = self.getImageByIndex(img_index, drc_index)
        v = p.EMVector
        d = EMVector2dict(v)
        return d

    def deleteAllImages(self) -> None:
        """Clears all images currently stored in EMMENU buffers."""
        for i, p in enumerate(self._emi):
            try:
                self._emi.DeleteImage(p)
            except BaseException:
                # sometimes EMMenu also loses track of image pointers...
                print(f'Failed to delete buffer {i} ({p})')

    def deleteImageByIndex(self, img_index: int, drc_index: int = None) -> int:
        """Delete the image from EMMENU by its index."""
        p = self.getImageByIndex(img_index, drc_index)
        self._emi.DeleteImage(p)  # alternative: self._emi.Remove(p.ImgHandle)

    def getImageByIndex(self, img_index: int, drc_index: int = None) -> int:
        """Grab data from the image manager by index. Return image pointer
        (COM).

        Not accessible through server.
        """
        if not drc_index:
            drc_index = self.drc_index

        p = self._immgr.Image(drc_index, img_index)

        return p

    def getImageDataByIndex(self, img_index: int, drc_index: int = None) -> 'np.array':
        """Grab data from the image manager by index.

        Return numpy 2D array
        """
        p = self.getImageByIndex(img_index, drc_index)

        tpe = p.DataType
        method = type_dict[tpe]

        f = getattr(p, method)
        arr = f()  # -> tuple of tuples

        return np.array(arr)

    def getCameraDimensions(self) -> (int, int):
        """Get the maximum dimensions reported by the camera."""
        # cfg = self.getCurrentConfig()
        # return cfg.DimensionX, cfg.DimensionY
        return self._cam.RealSizeX, self._cam.RealSizeY
        # return self._cam.MaximumSizeX, self._cam.MaximumSizeY

    def getImageDimensions(self) -> (int, int):
        """Get the dimensions of the image."""
        binning = self.getBinning()
        return int(self._cam.RealSizeX / binning), int(self._cam.RealSizeY / binning)

    def getPhysicalPixelsize(self) -> (int, int):
        """Returns the physical pixel size of the camera nanometers."""
        return self._cam.PixelSizeX, self._cam.PixelSizeY

    def getBinning(self) -> int:
        """Returns the binning corresponding to the currently selected camera
        config."""
        cfg = self.getCurrentConfig(as_dict=False)
        bin_x = cfg.BinningX
        bin_y = cfg.BinningY
        assert bin_x == bin_y, 'Binnings differ in X and Y direction! (X: {bin_x} | Y: {bin_y})'
        return bin_x

    def getCameraName(self) -> str:
        """Get the name reported by the camera."""
        return self._cam.name

    def writeTiffFromPointer(self, image_pointer, filename: str) -> None:
        """Write tiff file using the EMMENU machinery `image_pointer` is the
        memory address returned by `getImageIndex()`"""
        self._emf.WriteTiff(image_pointer, filename)

    def writeTiff(self, image_index, filename: str) -> None:
        """Write tiff file using the EMMENU machinery `image_index` is the
        index in the current directory of the image to be written."""
        drc_index = self.drc_index
        p = self.getImageByIndex(image_index, drc_index)

        self.writeTiffFromPointer(p, filename)

    def writeTiffs(self, start_index: int, stop_index: int, path: str, clear_buffer: bool = False) -> None:
        """Write a series of data in tiff format and writes them to the given
        `path` using EMMENU machinery."""
        path = Path(path)
        drc_index = self.drc_index

        if stop_index <= start_index:
            raise IndexError(f'`stop_index`: {stop_index} >= `start_index`: {start_index}')

        for i, image_index in enumerate(range(start_index, stop_index + 1)):
            p = self.getImageByIndex(image_index, drc_index)

            fn = str(path / f'{i:04d}.tiff')
            print(f'Image #{image_index} -> {fn}')

            # TODO: wrap writeTiff in try/except
            # writeTiff causes vague error if image does not exist

            self.writeTiffFromPointer(p, fn)

            if clear_buffer:
                # self._immgr.DeleteImageBuffer(drc_index, image_index)  # does not work on 3200
                self._emi.DeleteImage(p)  # also clears from buffer

        print(f'Wrote {i+1} images to {path}')

    def getImage(self, **kwargs) -> 'np.array':
        """Acquire image through EMMENU and return data as np array."""
        self._vp.AcquireAndDisplayImage()
        i = self.get_image_index()
        return self.getImageDataByIndex(i)

    def acquireImage(self, **kwargs) -> int:
        """Acquire image through EMMENU and store in the Image Manager Returns
        the image index."""
        self._vp.AcquireAndDisplayImage()
        return self.get_image_index()

    def set_image_index(self, index: int) -> None:
        """Change the currently selected buffer by the image index Note that
        the interface here is 0-indexed, whereas the image manager is 1-indexed
        (FIXME)"""
        self._vp.IndexInDirectory = index

    def get_image_index(self) -> int:
        """Retrieve the index of the currently selected buffer, 0-indexed."""
        return self._vp.IndexInDirectory

    def get_next_empty_image_index(self) -> int:
        """Get the next empty buffer in the image manager, 0-indexed."""
        i = self.get_image_index()
        while not self._immgr.ImageEmpty(self.drc_index, i):
            i += 1
        return i

    def stop_record(self) -> int:
        i = self.get_image_index()
        print(f'Stop recording (Image index={i})')
        self._vp.StopRecorder()
        self._recording = False
        return i

    def start_record(self) -> int:
        i = self.get_image_index()
        print(f'Start recording (Image index={i})')
        self._vp.StartRecorder()
        self._recording = True
        return i

    def stop_liveview(self) -> None:
        print('Stop live view')
        self._vp.StopContinuous()
        self._recording = False
        # StopRecorder normally defaults to top directory
        self._vp.DirectoryHandle = self.drc_index

    def start_liveview(self, delay: float = 3.0) -> None:
        print('Start live view')
        try:
            self._vp.StartContinuous()
        except comtypes.COMError as e:
            print(f'{e.details[1]}: {e.details[0]}')
        else:
            # sleep for a few seconds to ensure live view is running
            time.sleep(delay)

    def set_exposure(self, exposure_time: int) -> None:
        """Set exposure time in ms.

        It will be set to the lowest allowed value by EMMenu if the
        given exposure time is too low.
        """
        self._vp.ExposureTime = exposure_time

    def get_exposure(self) -> int:
        """Return exposure time in ms."""
        return self._vp.ExposureTime

    def set_autoincrement(self, toggle: bool) -> None:
        """Tell EMMENU to autoincrement the index number (True/False)"""
        if toggle:
            self._vp.AutoIncrement = 1
        else:
            self._vp.AutoIncrement = 0

    def get_timestamps(self, start_index: int, end_index: int) -> list:
        """Get timestamps in seconds for given image index range."""
        drc_index = self.drc_index
        timestamps = []
        for i, image_index in enumerate(range(start_index, end_index + 1)):
            p = self.getImageByIndex(image_index, drc_index)
            t = p.EMVector.lImgCreationTime
            timestamps.append(t)
        return timestamps

    def releaseConnection(self) -> None:
        """Release the connection to the camera."""
        self.stop_liveview()

        self._vp.DirectoryHandle = self.top_drc_index
        self._vp.SetCaption('Image')
        self.set_image_index(0)
        # self._immgr.DeleteDirectory(self.drc_index)  # bugged in EMMENU 5.0.9.0/5.0.10.0, FIXME later

        msg = f'Connection to camera `{self.getCameraName()}` ({self.name}) released'
        # print(msg)
        logger.info(msg)

        comtypes.CoUninitialize()


if __name__ == '__main__':
    cam = CameraEMMENU()

    from IPython import embed
    embed()
