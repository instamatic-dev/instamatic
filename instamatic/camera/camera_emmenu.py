from pathlib import Path

import time
import numpy as np
import logging
logger = logging.getLogger(__name__)

import atexit

from instamatic import config

import comtypes.client

import sys


type_dict = {
    1: "GetDataByte",
    2: "GetDataUShort",
    3: "GetDataShort",
    4: "GetDataLong",
    5: "GetDataFloat",
    6: "GetDataDouble",
    7: "GetDataComplex",
    8: "IMG_STRING",  # no method on EMImage
    8: "GEtDataBinary",
    9: "GetDataRGB8",
    10: "GetDataRGB16",
    11: "IMG_EMVECTOR"  # no method on EMImage
}


def EMVector2dict(v):
    """Convert EMVector object to a Python dictionary"""
    d = {}
    for k in dir(v):
        if k.startswith("_"):
            continue
        v = getattr(v, k)
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


class CameraEMMENU(object):
    """docstring for CameraEMMENU"""

    def __init__(self, drc_name="Instamatic data", interface="emmenu"):
        """Initialize camera module """
        super().__init__()

        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except WindowsError:
            comtypes.CoInitialize()

        self.name = interface

        self._obj = comtypes.client.CreateObject("EMMENU4.EMMENUApplication.1", comtypes.CLSCTX_ALL)

        self._recording = False

        # get first camera
        self._cam = self._obj.TEMCameras.Item(1)

        # hi-jack first viewport
        self._vp = self._obj.Viewports.Item(1)
        self._vp.SetCaption("Instamatic viewport")  # 2.5 ms
        self._vp.FlapState = 2  # pull out the flap, because we can :-) [0, 1, 2]

        self._obj.Option("ClearBufferOnDeleteImage")   # `Delete` -> Clear buffer (preferable)
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
        # if not self._immgr.DirectoryExist(self.top_drc_index, drc_name):
        #     self._immgr.CreateNewSubDirectory(self.top_drc_index, drc_name, 2, 2)
        if not self._immgr.DirectoryExist(self.top_drc_index, drc_name):
            # creating new subdirectories is bugged in EMMENU 5.0.9.0, FIXME later
            # raise exception for now until it is fixed
            raise ValueError(f"Directory `{drc_name}` does not exist in the EMMENU Image manager.")

        self.drc_name = drc_name
        self.drc_index = self._immgr.DirectoryHandleFromName(drc_name)
        
        self._vp.DirectoryHandle = self.drc_index  # set current directory

        self.load_defaults()

        msg = f"Camera `{self.getCameraName()}` ({self.name}) initialized"
        # print(msg)
        logger.info(msg)

        atexit.register(self.releaseConnection)

    def load_defaults(self) -> None:
        if self.name != config.cfg.camera:
            config.load(camera_name=self.name)

        self.__dict__.update(config.camera.d)

        self.streamable = False

    def listConfigs(self) -> None:
        """List the configs from the Configuration Manager"""
        print(f"Configurations for camera {self.name}")
        for i, cfg in enumerate(self._obj.CameraConfigurations):
            print(f"{i+1:2d} - {cfg.Name}")

    def getCurrentConfig(self) -> "ConfigObject":
        """Get selected config object currently associated with the viewport"""
        vp_cfg_name = self._vp.Configuration
        count = self._obj.CameraConfigurations.Count
        for j in range(1, count+1):
            cfg = self._obj.CameraConfigurations.Item(j)
            if cfg.Name == vp_cfg_name:
                return cfg

    def listDirectories(self) -> None:
        """List subdirectories of the top directory"""
        top_j = self._immgr.TopDirectory
        top_name = self._immgr.FullDirectoryName(top_j)
        print(f"{top_name} ({top_j})")

        drc_j = self._immgr.SubDirectory(top_j)

        while drc_j:
            drc_name = self._immgr.FullDirectoryName(drc_j)
            print(f"{drc_j} - {drc_name} ")

            drc_j = self._immgr.NextDirectory(drc_j)  # get next

    def getEMVectorByIndex(self, img_index: int, drc_index: int=None) -> dict:
        """Returns the EMVector by index as a python dictionary"""
        p = getImageByIndex(img_index, drc_index)
        v = p.EMVector
        d = EMVector2dict(v)
        return d

    def deleteAllImages(self) -> None:
        """Clears all images currently stored in EMMENU buffers"""
        for i, p in enumerate(self._emi):
            try:
                self._emi.DeleteImage(p)
            except:
                # sometimes EMMenu also loses track of image pointers...
                print(f"Failed to delete buffer {i} ({p})")

    def deleteImageByIndex(self, img_index: int, drc_index: int=None) -> int:
        """Delete the image from EMMENU by its index"""
        p = self.getImageByIndex(img_index, drc_index)
        self._emi.DeleteImage(p)  # alternative: self._emi.Remove(p.ImgHandle)

    def getImageByIndex(self, img_index: int, drc_index: int=None) -> int:
        """Grab data from the image manager by index. Return image pointer (COM)."""
        if not drc_index:
            drc_index = self.drc_index

        p = self._immgr.Image(drc_index, img_index)

        return p

    def getImageDataByIndex(self, img_index: int, drc_index: int=None) -> np.array:
        """Grab data from the image manager by index. Return numpy 2D array"""
        p = self.getImageByIndex(img_index, drc_index)

        tpe = p.DataType
        method = type_dict[tpe]

        f = getattr(p, method)
        arr = f()  # -> tuple of tuples
        
        return np.array(arr)

    def getDimensions(self) -> (int, int):
        """Get the maximum dimensions reported by the camera"""
        # cfg = self.getCurrentConfig()
        # return cfg.DimensionX, cfg.DimensionY
        return self._cam.RealSizeX, self._cam.RealSizeY
        # return self._cam.MaximumSizeX, self._cam.MaximumSizeY

    def getPhysicalPixelsize(self) -> (int, int):
        """Returns the physical pixel size of the camera nanometers"""
        return self._cam.PixelSizeX, self._cam.PixelSizeY

    def getBinning(self) -> (int, int):
        """Returns the binning corresponding to the currently selected camera config"""
        cfg = self.getCurrentConfig()
        return cfg.BinningX, cfg.BinningY

    def getCameraName(self) -> str:
        """Get the name reported by the camera"""
        return self._cam.name

    def writeTiff(self, image_pointer, filename: str) -> None:
        """Write tiff file using the EMMENU machinery
        `image_pointer` is the memory address returned by `getImageIndex()`

        TODO: write tiff from image_index instead of image_pointer??"""
        self._emf.WriteTiff(image_pointer, filename)

    def writeTiffs(self, start_index: int, stop_index: int, path: str, clear_buffer=True) -> None:
        """Write a series of data in tiff format and writes them to 
        the given `path` using EMMENU machinery"""
        path = Path(path)
        drc_index = self.drc_index
        for i, image_index in enumerate(range(start_index, stop_index+1)):
            p = self.getImageByIndex(image_index, drc_index)
            fn = str(path / f"{i:04d}.tiff")
            print(f"Image #{image_index} -> {fn}")
            self.writeTiff(p, fn)
    
            if clear_buffer:
                # self._immgr.DeleteImageBuffer(drc_index, image_index)  # does not work on 3200
                self._emi.DeleteImage(p)  # also clears from buffer

        print(f"Wrote {i+1} images to {path}")

    def getImage(self, **kwargs) -> np.array:
        """Acquire image through EMMENU and return data as np array"""
        self._vp.AcquireAndDisplayImage()
        i = self.get_image_index()
        return self.getImageDataByIndex(i)

    def acquireImage(self, **kwargs) -> int:
        """Acquire image through EMMENU and store in the Image Manager
        Returns the image index"""
        self._vp.AcquireAndDisplayImage()
        return self.get_image_index()

    def set_image_index(self, index: int) -> None:
        """Change the currently selected buffer by the image index
        Note that the interface here is 0-indexed, whereas the image manager is 1-indexed (FIXME)"""
        self._vp.IndexInDirectory = index

    def get_image_index(self) -> int:
        """Retrieve the index of the currently selected buffer, 0-indexed"""
        return self._vp.IndexInDirectory

    def get_next_empty_image_index(self) -> int:
        """Get the next empty buffer in the image manager, 0-indexed"""
        i = self.get_image_index()
        while not self._immgr.ImageEmpty(self.drc_index, i):
            i += 1        
        return i

    def stop_record(self) -> None:
        i = self.get_image_index()
        print(f"Stop recording (Image index={i})")
        self._vp.StopRecorder()
        self._recording = False

    def start_record(self) -> None:
        i = self.get_image_index()
        print(f"Start recording (Image index={i})")
        self._vp.StartRecorder()
        self._recording = True

    def stop_liveview(self) -> None:
        print("Stop live view")
        self._vp.StopContinuous()
        self._recording = False
        # StopRecorder normally defaults to top directory
        self._vp.DirectoryHandle = self.drc_index

    def start_liveview(self, delay=3.0) -> None:
        print("Start live view")
        self._vp.StartContinuous()

        # sleep for a few seconds to ensure live view is running
        time.sleep(delay)

    def set_exposure(self, exposure_time: int) -> None:
        """Set exposure time in ms"""
        self._vp.ExposureTime = exposure_time

    def get_exposure(self) -> int:
        """Return exposure time in ms"""
        return self._vp.ExposureTime

    def set_autoincrement(self, toggle: bool) -> None:
        """Tell EMMENU to autoincrement the index number (True/False)"""
        if toggle:
            self._vp.AutoIncrement = 1
        else:
            self._vp.AutoIncrement = 0

    def get_timestamps(self, start_index: int, end_index: int) -> list:
        """Get timestamps in seconds for given image index range"""
        drc_index = self.drc_index
        timestamps = []
        for i, image_index in enumerate(range(start_index, end_index+1)):
            p = self.getImageByIndex(image_index, drc_index)
            t = p.EMVector.lImgCreationTime
            timestamps.append(t)
        return timestamps

    def releaseConnection(self) -> None:
        """Release the connection to the camera"""
        self.stop_liveview()

        self._vp.DirectoryHandle = self.top_drc_index
        self._vp.SetCaption("Image")
        self.set_image_index(0)
        # self._immgr.DeleteDirectory(self.drc_index)  # bugged in EMMENU 5.0.9.0, FIXME later

        msg = f"Connection to camera `{self.getCameraName()}` ({self.name}) released" 
        # print(msg)
        logger.info(msg)

        comtypes.CoUninitialize()


if __name__ == '__main__':
    cam = CameraEMMENU()

    from IPython import embed
    embed()

