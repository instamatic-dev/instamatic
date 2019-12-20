from pathlib import Path
import re
import numpy as np
import random
from collections import defaultdict


# int
INTEGER = ("Color", "NumPts", "Draw", "Regis",
           "MapMontage", "MapSection", "MapBinning", "MapMagInd",
           "MapCamera", "ShutterMode", "MapSpotSize",
           "MapSlitIn", "ImageType", "MontUseStage",
           "MapProbeMode", "MapLDConSet", "Type", "GroupID",
           "MapID", "PieceOn", "Acquire", "DrawnID",
           "MontBinning", "SamePosId", "OrigReg",
           # mdoc
           "SpotSize",
           "Binning", "CameraIndex", "DividedBy2", "MagIndex",
           "Magnification", "ProbeMode", "MoveStage",
           "Alpha", "ImageSize", "DataMode", "Montage",
           "ImageSeries", "UsingCDS", "LowDoseConSet", "NumSubFrames",
           # other
           "Corner", "Imported", "K2ReadMode", "MapAlpha",
           "PolyID", "RealignReg", "RealignedID", "RegPt",
           "RegisteredToID", "RotOnLoad",
           # DE-12
           "DE12-TotalNumberOfFrames",
           "DE12-FramesPerSecond",
           "DE12-CameraPosition",
           "DE12-ProtectionCoverMode",
           "DE12-ProtectionCoverOpenDelay(ms)",
           "DE12-TemperatureDetector(C)",
           "DE12-SensorModuleSerialNumber",
           "DE12-SensorReadoutDelay(ms)",
           "DE12-IgnoredFramesInSummedImage",
           )

# float
FLOAT = ("MapExposure", "MapIntensity", "MapTiltAngle", "MapSettling",
         # .mdoc
         "StageZ", "PixelSpacing", "Defocus", "RotationAngle",
         "CountsPerElectron", "TargetDefocus", "TiltAngle", "ExposureTime",
         "DriftSettling", "Intensity", "ExposureDose", "PriorRecordDose",
         # other
         "DefocusOffset", "FocusAxisPos", "MapSlitWidth",
         # DE-12
         "DE12-ServerSoftwareVersion",
         "DE12-PreexposureTime(s)",
         "DE12-FaradayPlatePeakReading(pA/cm2)",
         )

# str
STRING = ("MapFile", "Note",
          # .mdoc
          "DateTime", "ImageFile", "NavigatorLabel",
          "SubFramePath", "ChannelName",
          )

# list, float
FLOAT_LIST = ("StageXYZ", "RawStageXY", "MapScaleMat", "XYinPc",
              "PtsX", "PtsY", "StageXYZ", "MapMinMaxScale",
              # .mdoc
              "StagePosition", "MinMaxMean", "XedgeDxyVS", "YedgeDxyVS",
              "XedgeDxy", "YedgeDxy", "ImageShift", "BufISXY",
              # other
              "BklshXY", "FocusOffsets", "LocalErrXY", "NetViewShiftXY",
              "RealignErrXY", "ViewBeamShiftXY", "ViewBeamTiltXY",
              "SuperMontCoords", "StageOffsets", "FrameDosesAndNumbers",
              "FilterSlitAndLoss",
              # external
              "CoordsInMap", "CoordsInAliMont", "CoordsInAliMontVS", "CoordsInPiece",
              )

# list, int
INTEGER_LIST = ("MapWidthHeight", "MapFramesXY",
                # .mdoc
                "PieceCoordinates", "AlignedPieceCoordsVS",
                "AlignedPieceCoords", "MontBacklash",
                "ValidBacklash", "CameraModes", "FilterState",
                "ConSetUsed", "MultishotHoleAndPosition",
                # other
                "HoleArray", "LDAxisAngle", "SkipHoles",
                "SuperMontXY",
                )

UNDEFINED = ()


class NavItem(object):
    """
    DataClass for SerialEM Nav items

    Type:
        0: Marker
        1: Polygon
        2: Map
    """

    TAG_ID_ITERATOR = 1
    # MAP_ID_ITERATOR = 1

    def __init__(self, d: dict, tag: str):
        super().__init__()
        # if not "MapID" in d:
        #     d["MapID"] = NavItem.MAP_ID_ITERATOR
        #     NavItem.MAP_ID_ITERATOR += 1

        self._keys = tuple(d.keys())

        self.Acquire = 0
        self.__dict__.update(d)

        if not tag:
            tag = f"Item-{NavItem.TAG_ID_ITERATOR}"
            NavItem.TAG_ID_ITERATOR += 1

        self.tag = tag

    def __repr__(self):
        return f"{self.__class__.__name__}({self.kind}[Item = {self.tag}])"

    @property
    def kind(self) -> str:
        return ("Marker", "Polygon", "Map")[self.Type]

    @property
    def stage_x(self) -> float:
        return self.StageXYZ[0]

    @property
    def stage_y(self) -> float:
        return self.StageXYZ[1]

    @property
    def stage_z(self) -> list:
        return self.StageXYZ[2]

    @property
    def stage_xy(self) -> list:
        return self.StageXYZ[0:2]

    def to_string(self) -> str:
        """Convert nav item to string that can be printed to .nav file"""
        s = f"[Item = {self.tag}]\n"

        d = self.to_dict()

        for key in sorted(d.keys()):
            val = d[key]

            try:
                if key in INTEGER:
                    val = str(val)
                elif key in FLOAT:
                    val = str(val)
                elif key in FLOAT_LIST:
                    val = " ".join([str(x) for x in val])
                elif key in INTEGER_LIST:
                    val = " ".join([str(x) for x in val])
            except TypeError as e:
                print(e)
                print(key, val)

            s += f"{key} = {val}\n"

        s += ""

        return s

    def to_dict(self) -> dict:
        """Convert nav item back to dictionary"""
        return {key: self.__dict__[key] for key in self._keys}


class ClassName(object):
    """docstring for ClassName"""

    def __init__(self, arg):
        super(ClassName, self).__init__()
        self.arg = arg


class MapItem(NavItem):
    """Adds some extra methods for map items"""

    GROUP_ID_ITERATOR = random.randint(1, 90000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.markers = {}

    @property
    def map_scale_matrix(self) -> "np.array":
        MapBinning = self.MapBinning
        MontBinning = self.MontBinning
        mat = (MapBinning / MontBinning) * np.array(self.MapScaleMat).reshape(2, 2)
        return mat.T

    @property
    def stagematrix(self) -> "np.array":
        """Alias for map_scale_matrix"""
        return self.map_scale_matrix

    def pixel_to_stagecoords(self, coords: list) -> "np.array":
        """Convert from pixel coordinates to stage coordinates"""
        coords = np.array(coords)
        cp = np.array(self.MapWidthHeight) / 2
        cs = np.array(self.StageXYZ)[0:2]
        mati = np.linalg.inv(self.map_scale_matrix)

        return np.dot(coords - cp, mati) + cs

    def stage_to_pixelcoords(self, coords: list) -> "np.array":
        """Convert from stage coordinates to pixel coordinates"""
        coords = np.array(coords)
        cp = np.array(self.MapWidthHeight) / 2
        cs = np.array(self.StageXYZ)[0:2]
        mat = self.map_scale_matrix

        return np.dot(coords - cs, mat) + cp

    def load_image(self, drc: str = None) -> "np.array":
        """Loads the image corresponding to this item"""
        import mrcfile

        if not drc:
            drc = "."
        drc = Path(drc)

        map_file = Path(self.MapFile)
        if not map_file.exists():
            map_file = drc / Path(self.MapFile).name

        m = mrcfile.mmap(map_file)
        s = self.MapSection
        return np.array(m.data[s])

    def plot_image(self, markers: bool = True) -> None:
        """Plot the image including markers (optional)"""
        import matplotlib.pyplot as plt

        if markers is True:
            markers = self.markers.values()
        elif isinstance(markers, dict):
            markers = markers.values()
        elif isinstance(markers, (list, tuple, np.ndarray)):
            pass
        else:
            markers = []

        im = self.load_image()
        plt.matshow(im, vmax=np.percentile(im, 99))
        yres = self.MapWidthHeight[1]

        coords = []
        for marker in markers:
            if isinstance(marker, NavItem):
                xy = np.array([marker.stage_x, marker.stage_y])
                px, py = self.stage_to_pixelcoords(xy)
                py = yres - py
            else:
                py, px = marker

            coords.append((px, py))

        if coords:
            px, py = np.array(coords).T
            plt.plot(px, py, "ro", markerfacecolor='none', markersize=20, markeredgewidth=2)

    def add_marker(self, coord, tag=None, acquire=True) -> "NavItem":
        """Add pixel coordinate (numpy) as marker to a map item"""

        # assuming pixel coords from numpy
        py, px = coord
        yres = self.MapWidthHeight[1]
        py = yres - py
        stage_x, stage_y = self.pixel_to_stagecoords((px, py))

        d = {}
        try:
            d["BklshXY"] = self.BklshXY
        except AttributeError:
            d["BklshXY"] = 10, -10
        d["Color"] = 0
        d["DrawnID"] = self.MapID
        d["GroupID"] = MapItem.GROUP_ID_ITERATOR
        # d["MapID"] = 1 + self.i  # must be a unique ID under 100000 [optional, default=0]
        d["Acquire"] = int(acquire)
        d["NumPts"] = 1
        d["PtsX"] = [stage_x]
        d["PtsY"] = [stage_y]
        d["Regis"] = self.Regis
        d["StageXYZ"] = [stage_x, stage_y, self.stage_z]
        d["Type"] = 0

        item = NavItem(d, tag=tag)

        self.markers[item.tag] = item

        return item

    def add_marker_group(self, coords, acquire=True, replace=True) -> list:
        """Add pixel coordinates (numpy) as markers to a map item
        If `replace==True`, replace the entire list of existing markers
        on the map item."""
        if replace:
            self.markers = {}

        ret = []
        for i, coord in enumerate(coords):
            tag = f"{self.tag}-{i}"
            item = self.add_marker(coord, tag=tag, acquire=True)
            ret.append(item)

        MapItem.GROUP_ID_ITERATOR += 1

        return ret

    def update_markers(self, *items):
        """Update the list of markers belonging to this `Map` with
        the given items."""
        for item in items:
            self.markers[item.tag] = item

    def set_markers(self, *items):
        """Replace the list of markers belonging to this `Map` with
        the given items."""
        self.markers = {}
        self.update_markers(*items)


def block2dict(block: list, kind: str = None, sequence: int = -1) -> dict:
    """Takes a text block from a SerialEM .nav file and converts it into a
    dictionary"""
    patt_split = re.compile("\s?=\s?")
    d = {}

    for item in block:
        key, value = re.split(patt_split, item)

        try:
            if key in INTEGER:
                value = int(value)
            elif key in FLOAT:
                value = float(value)
            elif key in STRING:
                value = str(value)
            elif key in FLOAT_LIST:
                value = [float(val) for val in value.split()]
            elif key in INTEGER_LIST:
                value = [int(val) for val in value.split()]
            elif key in UNDEFINED:
                print(item)
            else:
                print("Unknown item:", item)
        except Exception as e:
            print(e)
            print(item)
            print(key, value)
            raise

        d[key] = value

    if sequence >= 0:
        d["sequence"] = sequence
    if kind:
        d["kind"] = kind

    return d


def block2nav(block: list, tag=None) -> "NavItem":
    """Takes a text block from a SerialEM .nav file and converts it into a
    instance of `NavItem` or `MapItem`"""
    d = block2dict(block)
    kind = d["Type"]

    if kind == 2:
        ret = MapItem(d, tag=tag)
    else:
        ret = NavItem(d, tag=tag)

    return ret


def read_nav_file(fn: str, acquire_only: bool = False) -> list:
    """
    Reads a SerialEM .nav file and returns a list of dictionaries
    containing nav item data.

    acquire_only: bool
        read only files with the Acquire tag set
    """

    # https://regex101.com/
    patt_match = re.compile("\[Item\s?=\s?([a-zA-Z0-9_-]*)\]")

    capture = False
    block = []
    items = []
    tag = ""

    f = open(fn, "r")
    for line in f:
        line = line.strip()
        if not line:
            continue

        m = re.match(patt_match, line)

        if m:
            if block:
                items.append(block2nav(block, tag=tag))

            # prep for next block
            tag = m.groups()[0]
            block = []
            capture = True
        elif capture:
            block.append(line)
        else:
            if line.startswith("AdocVersion"):
                pass
            elif line.startswith("LastSavedAs"):
                pass
            else:
                print(line)

    items.append(block2nav(block, tag=tag))

    if acquire_only:
        items = [item for item in items if item.Acquire]

    # associate markers with map items
    map_items = (item for item in items if item.kind == "Map")
    markers = (item for item in items if item.kind == "Marker")

    d = defaultdict(list)

    for marker in markers:
        d[marker.DrawnID].append(marker)

    for map_item in map_items:
        markers = d[map_item.MapID]
        map_item.update_markers(*markers)

    return items


def write_nav_file(fn: str, *items, mode="w") -> None:
    """
    Write list of nav items to a navigator file with filename `fn` to be read by SerialEM

    `items` must be a list of NavItem / MapItem objects

    mode can be "w" to write a new file, or "a" to append
    items to an existing file
    """
    f = open(fn, mode) if fn else None
    version = "2.00"

    if mode == "w":
        print(f"AdocVersion = {version}", file=f)
        print(f"LastSavedAs = {fn}", file=f)
        print("", file=f)

    for item in items:
        print(item.to_string(), file=f)


def read_mdoc_file(fn: str, only_kind: str = None) -> list:
    """
    Reads a SerialEM .mdoc file and returns a list of dictionaries
    containing supporting data.

    Parameters
    ----------
    only_kind : str
        Return only items of this kind, i.e. ZValue or MontSection (case-insensitive)

    Returns:
    --------
    List of dicts with header information from the .mdoc file
    """

    # https://regex101.com/
    patt_match = re.compile("\[([a-zA-Z]+)\s?=\s?([0-9]+)\]")

    capture = False
    block = []
    items = []
    tag = ""
    kind = None

    f = open(fn, "r")
    for line in f:
        line = line.strip()
        if not line:
            continue

        m = re.match(patt_match, line)

        if m:
            if block:
                items.append(block2dict(block, kind=kind, sequence=sequence))

            # prep for next block
            kind = m.groups()[0]
            sequence = int(m.groups()[1])

            block = []
            capture = True
        elif capture:
            block.append(line)
        else:
            print(line)

    items.append(block2dict(block, kind=kind, sequence=sequence))

    if only_kind:
        only_kind = only_kind.lower()
        items = [item for item in items if item["kind"].lower() == only_kind]

    return items


if __name__ == '__main__':
    fn = "C:/s/work_2019-06-26/navs2.nav"
    items = read_nav_file(fn)

    breakpoint()
