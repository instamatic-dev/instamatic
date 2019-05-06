from pathlib import Path

import time
import numpy as np
import logging
logger = logging.getLogger(__name__)

import atexit

from instamatic import config

import comtypes.client

import sys

type_dct = {
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

        # get first camera
        self._cam = self.obj.TEMCameras.Item(1)

        # hi-jack first viewport
        self._vp = obj.Viewports.Item(1)
        self._vp.SetCaption("Instamatic viewport")  # 2.5 ms

        c.obj.Option("ClearBufferOnDeleteImage")   # `Delete` -> Clear buffer (preferable)
                                                   # other choices: DeleteBufferOnDeleteImage / Default
        
        # Image manager for managing image buffers (left panel)
        self._immgr = c.obj.ImageManager 

        # for writing tiff files
        self._emf = c.obj.EMFile

        # set up instamatic data directory
        self.top_drc_index = im.TopDirectory 
        self.top_drc_name = self._immgr.DirectoryName(self.top_drc_index)
        
        im.CreateNewSubDirectory(t, drc_name, 2, 2)
        self.drc_name = drc_name
        self.drc_index = im.DirectoryHandleFromName(drc_name)
        
        self._vp.DirectoryHandle = self.drc_index  # set current directory

        self.load_defaults()

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
        print(f"Configurations for camera {self.getName}")
        count = c.obj.CameraConfigurations.Count
        for j in range(1, count+1):
            cfg = c.obj.CameraConfigurations.Item(j)
            print(f"{j:02d} - {cfg.Name}")

    def listDirectories(self):
        """List subdirectories of the top directory"""
        top_j = im.TopDirectory()
        top_name = FullDirectorName(top_j)
        print(f"{top_name} ({top_j})")

        drc_j = im.SubDirectory(top_j)

        while drc_j:
            drc_name = FullDirectorName(drc_j)
            print(f"{drc_name} ({drc_j})")

            drc_j = im.NextDirectory(drc_j)  # get next

    def getImageByIndex(self, img_index: int, drc_index: int=None) -> int:
        """Grab data from the image manager by index. Return image pointer (COM)."""
        if not drc:
            drc_index = self.drc_index

        p = im.Image(drc_index, img_index)

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
        """Get the dimensions reported by the camera"""
        return self._cam.RealSizeX, self._cam.RealSizeY

    def getPixelsize(self) -> (int, int):
        return self._cam.PixelSizeX, self._cam.PixelSizeY

    def getName(self) -> str:
        """Get the name reported by the camera"""
        return self._cam.name

    def writeTiff(self, image_pointer, filename):
        """Write tiff file using the EMMENU machinery"""
        return self._emf.WriteTiff(image_pointer, filename)

    def writeTiffs(self, start_index: int, stop_index: int, path: str, clear_buffer=True):
        """Write a series of data in tiff format and writes them to 
        the given `path` using EMMENU machinery"""
        path = Path(path)
        drc = self.drc_index
        for i, image_index in enumerate(range(start_index, stop_index+1)):
            p = self.getImageByIndex(j, drc)
            fn = str(path / "{i:04d}.tiff")
            print(f"Image #{image_index} -> {fn}")
            self.writeTiff(p, fn)
    
            if clear_buffer:
                self._immgr.DeleteImageBuffer(d, j)

        print(f"Wrote {i+1} images to {path}")

    def getImage(self, **kwargs):
        raise NotImplementedError

    @property
    def image_index(self):
        return self._vp.IndexInDirectory

    @property.setter
    def image_index(self, value):
        self._vp.IndexInDirectory = value

    def acquire(self):
        self._vp.AcquireAndDisplayImage()

    def stop_record(self):
        i = self.image_index
        print("Stop recording (Image index={i})")
        self._vp.StopRecorder()
        self._recording = False

    def start_record(self):
        i = self.image_index
        print("Start recording (Image index={i})")
        self._vp.StartRecorder()
        self._recording = True

    def stop_liveview(self):
        print("Stop live view")
        self._vp.StopContinuous()
        self._recording = False
        # StopContinuous normally defaults to top directory
        self._vp.DirectoryHandle = self.drc_index

    def start_liveview(self, delay=2.0):
        print("Start live view")
        self._vp.StartContinuous()

        # sleep for a few seconds to ensure live view is running
        time.sleep(delay)

    def releaseConnection(self) -> None:
        """Release the connection to the camera"""
        comtypes.CoUninitialize()
        
        self._vp.DirectoryHandle = self.top_drc_index
        self.image_index = 0
        self._immgr.DeleteDirectory(self.drc_index)

        name = self.getName()
        msg = f"Connection to camera '{name}' released" 
        logger.info(msg)


if __name__ == '__main__':
    cam = CameraEMMENU()

    from IPython import embed
    embed()

