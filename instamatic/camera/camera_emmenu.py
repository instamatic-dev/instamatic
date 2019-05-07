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
    8: "IMG_STRING",
    8: "GEtDataBinary",
    9: "GetDataRGB8",
    10: "GetDataRGB16",
    11: "IMG_EMVECTOR"
}


class CameraEMMENU(object):
    """docstring for CameraEMMENU"""

    def __init__(self, drc_name="Instamatic data"):
        """Initialize camera module """
        super().__init__()

        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except WindowsError:
            comtypes.CoInitialize()

        self.obj = comtypes.client.CreateObject("EMMENU4.EMMENUApplication.1", comtypes.CLSCTX_ALL)

        self._recording = False

        # get first camera
        self._cam = self.obj.TEMCameras.Item(1)

        # hi-jack first viewport
        self._vp = self.obj.Viewports.Item(1)
        self._vp.SetCaption("Instamatic viewport")  # 2.5 ms

        self.obj.Option("ClearBufferOnDeleteImage")   # `Delete` -> Clear buffer (preferable)
                                                      # other choices: DeleteBufferOnDeleteImage / Default
        
        # Image manager for managing image buffers (left panel)
        self._immgr = self.obj.ImageManager 

        # for writing tiff files
        self._emf = self.obj.EMFile

        # set up instamatic data directory
        self.top_drc_index = self._immgr.TopDirectory 
        self.top_drc_name = self._immgr.DirectoryName(self.top_drc_index)
        
        # check if exists
        if not self._immgr.DirectoryExist(self.top_drc_index, drc_name):
            self._immgr.CreateNewSubDirectory(self.top_drc_index, drc_name, 2, 2)
        self.drc_name = drc_name
        self.drc_index = self._immgr.DirectoryHandleFromName(drc_name)
        
        self._vp.DirectoryHandle = self.drc_index  # set current directory

        # self.load_defaults()  # TODO: how to deal with config?

        msg = f"Camera {self.getName()} initialized"
        logger.info(msg)

        atexit.register(self.releaseConnection)

    def load_defaults(self):
        if self.name != config.cfg.camera:
            config.load(camera_name=self.name)

        self.__dict__.update(config.camera.d)

        self.streamable = False

    def listConfigs(self):
        """List the configs from the Configuration Manager"""
        print(f"Configurations for camera {self.name}")
        count = self.obj.CameraConfigurations.Count
        for j in range(1, count+1):
            cfg = self.obj.CameraConfigurations.Item(j)
            print(f"{j:2d} - {cfg.Name}")

    def getCurrentConfig(self):
        """Get selected config object currently associated with the viewport"""
        vp_cfg_name = self._vp.Configuration
        count = self.obj.CameraConfigurations.Count
        for j in range(1, count+1):
            cfg = self.obj.CameraConfigurations.Item(j)
            if cfg.Name == vp_cfg_name:
                return cfg

    def listDirectories(self):
        """List subdirectories of the top directory"""
        top_j = self._immgr.TopDirectory
        top_name = self._immgr.FullDirectoryName(top_j)
        print(f"{top_name} ({top_j})")

        drc_j = self._immgr.SubDirectory(top_j)

        while drc_j:
            drc_name = self._immgr.FullDirectoryName(drc_j)
            print(f"{drc_j} - {drc_name} ")

            drc_j = self._immgr.NextDirectory(drc_j)  # get next

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
        """In nanometers"""
        return self._cam.PixelSizeX, self._cam.PixelSizeY

    def getBinning(self) -> (int, int):
        cfg = self.getCurrentConfig()
        return cfg.BinningX, cfg.BinningY

    def getName(self) -> str:
        """Get the name reported by the camera"""
        return self._cam.name

    @property
    def name(self) -> str:
        """Get the name reported by the camera"""
        return self.getName()

    def writeTiff(self, image_pointer, filename):
        """Write tiff file using the EMMENU machinery

        TODO: write tiff from image_index instead of image_pointer??"""
        return self._emf.WriteTiff(image_pointer, filename)

    def writeTiffs(self, start_index: int, stop_index: int, path: str, clear_buffer=True):
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
                self._immgr.DeleteImageBuffer(drc_index, image_index)

        print(f"Wrote {i+1} images to {path}")

    def getImage(self, **kwargs) -> np.array:
        """Acquire image through EMMENU and return data as np array"""
        self._vp.AcquireAndDisplayImage()
        i = self.image_index
        return self.getImageDataByIndex(i)  # TODO: header

    def acquireImage(self, **kwargs) -> int:
        """Acquire image through EMMENU and store in the Image Manager
        Returns the image index"""
        self._vp.AcquireAndDisplayImage()
        return self.image_index

    @property
    def image_index(self) -> int:
        """0-indexed"""
        return self._vp.IndexInDirectory

    @image_index.setter
    def image_index(self, value: int):
        """0-indexed"""
        self._vp.IndexInDirectory = value

    def stop_record(self):
        i = self.image_index
        print(f"Stop recording (Image index={i})")
        self._vp.StopRecorder()
        # StopContinuous normally defaults to top directory
        self._vp.DirectoryHandle = self.drc_index
        self._recording = False

    def start_record(self):
        i = self.image_index
        print(f"Start recording (Image index={i})")
        self._vp.StartRecorder()
        self._recording = True

    def stop_liveview(self):
        print("Stop live view")
        self._vp.StopContinuous()
        self._recording = False
        # StopContinuous normally defaults to top directory
        # self._vp.DirectoryHandle = self.drc_index

    def start_liveview(self, delay=3.0):
        print("Start live view")
        self._vp.StartContinuous()

        # sleep for a few seconds to ensure live view is running
        time.sleep(delay)

    def set_exposure(self, exposure_time: int):
        """Set exposure time in ms"""
        self._vp.ExposureTime = exposure_time

    def get_exposure(self):
        """Return exposure time in ms"""
        return self._vp.ExposureTime

    def get_timestamps(self, start_index: int, end_index: int) -> list:
        """Get timestamps in seconds for given image index range"""
        drc_index = self.drc_index
        timestamps = []
        for i, image_index in enumerate(range(start_index, stop_index+1)):
            p = self.getImageByIndex(image_index, drc_index)
            t = p.EMVector.lImgCreationTime
            timestamps.append(t)
        return timestamps

    def releaseConnection(self) -> None:
        """Release the connection to the camera"""
        self.stop_liveview()

        self._vp.DirectoryHandle = self.top_drc_index
        self.image_index = 0
        self._immgr.DeleteDirectory(self.drc_index)

        name = self.getName()
        msg = f"Connection to camera '{name}' released" 
        logger.info(msg)

        comtypes.CoUninitialize()

if __name__ == '__main__':
    cam = CameraEMMENU()

    # cam._vp.EMVectorHandle ?
    # cam._vp.ImageHandle ?

    from IPython import embed
    embed()

