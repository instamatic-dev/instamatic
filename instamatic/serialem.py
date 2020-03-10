import random
import re
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patches

from instamatic.tools import bin_ndarray


# int
INTEGER = ('Color', 'NumPts', 'Draw', 'Regis',
           'MapMontage', 'MapSection', 'MapBinning', 'MapMagInd',
           'MapCamera', 'ShutterMode', 'MapSpotSize',
           'MapSlitIn', 'ImageType', 'MontUseStage',
           'MapProbeMode', 'MapLDConSet', 'Type', 'GroupID',
           'MapID', 'PieceOn', 'Acquire', 'DrawnID',
           'MontBinning', 'SamePosId', 'OrigReg',
           # mdoc
           'SpotSize',
           'Binning', 'CameraIndex', 'DividedBy2', 'MagIndex',
           'Magnification', 'ProbeMode', 'MoveStage',
           'Alpha', 'ImageSize', 'DataMode', 'Montage',
           'ImageSeries', 'UsingCDS', 'LowDoseConSet', 'NumSubFrames',
           # other
           'Corner', 'Imported', 'K2ReadMode', 'MapAlpha',
           'PolyID', 'RealignReg', 'RealignedID', 'RegPt',
           'RegisteredToID', 'RotOnLoad',
           # DE-12
           'DE12-TotalNumberOfFrames',
           'DE12-FramesPerSecond',
           'DE12-CameraPosition',
           'DE12-ProtectionCoverMode',
           'DE12-ProtectionCoverOpenDelay(ms)',
           'DE12-TemperatureDetector(C)',
           'DE12-SensorModuleSerialNumber',
           'DE12-SensorReadoutDelay(ms)',
           'DE12-IgnoredFramesInSummedImage',
           )

# float
FLOAT = ('MapExposure', 'MapIntensity', 'MapTiltAngle', 'MapSettling',
         # .mdoc
         'StageZ', 'PixelSpacing', 'Defocus', 'RotationAngle',
         'CountsPerElectron', 'TargetDefocus', 'TiltAngle', 'ExposureTime',
         'DriftSettling', 'Intensity', 'ExposureDose', 'PriorRecordDose',
         # other
         'DefocusOffset', 'FocusAxisPos', 'MapSlitWidth',
         # DE-12
         'DE12-ServerSoftwareVersion',
         'DE12-PreexposureTime(s)',
         'DE12-FaradayPlatePeakReading(pA/cm2)',
         )

# str
STRING = ('MapFile', 'Note',
          # .mdoc
          'DateTime', 'ImageFile', 'NavigatorLabel',
          'SubFramePath', 'ChannelName',
          )

# list, float
FLOAT_LIST = ('StageXYZ', 'RawStageXY', 'MapScaleMat', 'XYinPc',
              'PtsX', 'PtsY', 'StageXYZ', 'MapMinMaxScale',
              # .mdoc
              'StagePosition', 'MinMaxMean', 'XedgeDxyVS', 'YedgeDxyVS',
              'XedgeDxy', 'YedgeDxy', 'ImageShift', 'BufISXY',
              # other
              'BklshXY', 'FocusOffsets', 'LocalErrXY', 'NetViewShiftXY',
              'RealignErrXY', 'ViewBeamShiftXY', 'ViewBeamTiltXY',
              'SuperMontCoords', 'StageOffsets', 'FrameDosesAndNumbers',
              'FilterSlitAndLoss',
              # external
              'CoordsInMap', 'CoordsInAliMont', 'CoordsInAliMontVS', 'CoordsInPiece',
              )

# list, int
INTEGER_LIST = ('MapWidthHeight', 'MapFramesXY',
                # .mdoc
                'PieceCoordinates', 'AlignedPieceCoordsVS',
                'AlignedPieceCoords', 'MontBacklash',
                'ValidBacklash', 'CameraModes', 'FilterState',
                'ConSetUsed', 'MultishotHoleAndPosition',
                # other
                'HoleArray', 'LDAxisAngle', 'SkipHoles',
                'SuperMontXY',
                )

UNDEFINED = ()

REQUIRED_MAPITEM = ('StageXYZ', 'MapFile', 'MapSection',
                    'MapBinning', 'MapMagInd', 'MapScaleMat',
                    'MapWidthHeight', 'Color', 'Regis',
                    'Type', 'MapID', 'MapMontage', 'MapCamera',
                    'NumPts', 'PtsX', 'PtsY',
                    )


def stitch_map_items(items: list,
                     vmin: int = None,
                     vmax: int = None,
                     binning: int = 16,
                     markers: list = None,
                     scatter_kwargs: dict = {},
                     color: str = 'red',
                     label: bool = True,
                     ) -> None:
    """Take a list of MapItems and plot them at scale with respect to each
    other.

    Parameters
    ----------
    vmax : int
        Passed to plt.imshow to tune the contrast.
    vmin : int
        Passed to plt.imshow to tune the contrast.
    binning : int
        Bin the loaded images before displaying them to save
        on memory and computation times
    markers: list of arrays (Mx2)
        Must be the same length as `items`. Each item in markers
        is a numpy array (Mx2) containing x/y pixel coordinates (i.e. of
        particle positions) to plot on the stitched map.
    scatter_kwargs: dict
        Passed to `plt.scatter` to style the points passed using
        `markers`.
    color: str
        Color of all the decorations (markers, borders, text)
    label: bool
        Label each frame with the sequence number
    """
    _scatter_kwargs = {
        'marker': '.',
        'color': 'blue',
        's': 2,
    }

    _scatter_kwargs.update(scatter_kwargs)

    positions = []

    fig, ax = plt.subplots()

    tag_min = min(int(item.tag) for item in items)

    xy_coords = []

    for i, item in enumerate(items):
        sx, sy = item.stage_xy
        pos_x, pos_y = item.stage_to_pixelcoords((sx / 1000, sy / 1000))

        img = item.load_image()

        if binning:
            img = bin_ndarray(img, binning=binning)
            pos_x /= binning
            pos_y /= binning

        positions.append((pos_x, pos_y))

        shape_x, shape_y = img.shape
        shape_x = shape_x // 2
        shape_y = shape_y // 2

        im = ax.imshow(img,
                       interpolation='bilinear',
                       extent=[pos_y - shape_y, pos_y + shape_y, pos_x - shape_x, pos_x + shape_x],
                       clip_on=True,
                       vmax=vmax, vmin=vmin)

        rect = patches.Rectangle((pos_y - shape_y, pos_x - shape_x), shape_y * 2, shape_x * 2,
                                 fill=False,
                                 edgecolor=color,
                                 linewidth=1)
        ax.add_patch(rect)

        if label:
            ax.text(pos_y, pos_x, str(int(item.tag) - tag_min), ha='center', va='center', color=color)

        if markers:
            xy_coord = markers[i]
            xy_coord = np.array((-1, 1)) * xy_coord / binning + np.array((pos_x, pos_y)) - np.array((-shape_x, shape_y))
            xy_coords.append(xy_coord)

    ax.scatter(0, 0, color=color, marker='+', label='Origin')
    title = f'Overview of {len(items)} frames'

    if markers:
        xy_coords = np.vstack(xy_coords)
        x, y = xy_coords.T

        n_tot = len(xy_coords)
        n_avg = len(xy_coords) / len(items)
        ax.scatter(y, x, **_scatter_kwargs, label='Particles')
        title += f'\n{n_tot} particles (average: {n_avg:.3f} / frame)'

    positions = np.array(positions)
    xmin, ymin = positions.min(axis=0)
    xmax, ymax = positions.max(axis=0)
    ax.set_ylim(xmin - shape_x, xmax + shape_x)
    ax.set_xlim(ymin - shape_x, ymax + shape_y)
    ax.axis('off')
    plt.title(title)
    plt.show()


def item_to_string(d: dict, tag: str):
    """Turn a SerialEM key/values dictionary into a .mdoc/.nav formatted
    string."""
    s = f'[Item = {tag}]\n'

    for key in sorted(d.keys()):
        val = d[key]

        try:
            if key in INTEGER:
                val = str(val)
            elif key in FLOAT:
                val = str(val)
            elif key in FLOAT_LIST:
                val = ' '.join([str(x) for x in val])
            elif key in INTEGER_LIST:
                val = ' '.join([str(x) for x in val])
        except TypeError as e:
            print(e)
            print(key, val)

        s += f'{key} = {val}\n'

    s += ''
    return s


class NavItem:
    """DataClass for SerialEM Nav items.

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
            tag = f'Item-{NavItem.TAG_ID_ITERATOR}'
            NavItem.TAG_ID_ITERATOR += 1

        self.tag = tag

    def __repr__(self):
        return f'{self.__class__.__name__}({self.kind}[Item = {self.tag}])'

    @property
    def kind(self) -> str:
        return ('Marker', 'Polygon', 'Map')[self.Type]

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
        """Convert nav item to string that can be printed to .nav file."""
        d = self.to_dict()
        return item_to_string(d, tag=self.tag)

    def to_dict(self) -> dict:
        """Convert nav item back to dictionary."""
        return {key: self.__dict__[key] for key in self._keys}

    @property
    def color_rgba(self) -> tuple:
        """Return matplotlib RGBA color."""
        return mpl.colors.to_rgba(self.color_str, alpha=None)

    @property
    def color_str(self) -> str:
        """Return color as string."""
        return ('red', 'green', 'blue', 'yellow', 'magenta', 'black')[self.Color]


class MapItem(NavItem):
    """Adds some extra methods for map items."""

    GROUP_ID_ITERATOR = random.randint(1, 90000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.validate()
        self.markers = {}

    @property
    def map_scale_matrix(self) -> 'np.array':
        # MapScaleMat already has binning embedded
        # MapBinning = self.MapBinning

        try:
            MontBinning = self.MontBinning
        except AttributeError:
            MontBinning = 1
        mat = (1 / MontBinning) * np.array(self.MapScaleMat).reshape(2, 2)
        return mat.T

    @property
    def stagematrix(self) -> 'np.array':
        """Alias for map_scale_matrix."""
        return self.map_scale_matrix

    def pixel_to_stagecoords(self, coords: list) -> 'np.array':
        """Convert from pixel coordinates to stage coordinates."""
        coords = np.array(coords)
        cp = np.array(self.MapWidthHeight) / 2
        cs = np.array(self.StageXYZ)[0:2]
        mati = np.linalg.inv(self.map_scale_matrix)

        return np.dot(coords - cp, mati) + cs

    def stage_to_pixelcoords(self, coords: list) -> 'np.array':
        """Convert from stage coordinates to pixel coordinates."""
        coords = np.array(coords)
        cp = np.array(self.MapWidthHeight) / 2
        cs = np.array(self.StageXYZ)[0:2]
        mat = self.map_scale_matrix

        return np.dot(coords - cs, mat) + cp

    def load_image(self, drc: str = None) -> 'np.array':
        """Loads the image corresponding to this item."""
        import mrcfile

        if not drc:
            drc = '.'
        drc = Path(drc)

        map_file = Path(self.MapFile)
        if not map_file.exists():
            map_file = drc / Path(self.MapFile).name

        m = mrcfile.mmap(map_file)
        s = self.MapSection
        if m.is_single_image() and s == 0:
            return np.array(m.data)
        else:
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
            plt.plot(px, py, 'ro', markerfacecolor='none', markersize=20, markeredgewidth=2)

    def add_marker(self,
                   coord: tuple,
                   kind: str = 'pixel',
                   tag: str = None,
                   acquire: bool = True,
                   ) -> 'NavItem':
        """Add pixel or stage coordinate as marker to a map item. Markers are
        linked to this `MapItem` via the `.markers` attribute.

        Parameters
        ----------
        coord : array (n x 2)
            List of X, Y pixel coordinates or stage coordinates corresponding to the navigation item.
        kind : str
            Defines the kind of coordinate supplied, must be one of `pixel` or `stage`. Stage coordinates
            are given in μm.
        tag : str
            Simple name tag for the item. It will be generated automatically if it is not given.
        acquire : bool
            Turn on the acquire flag for this item.

        Returns
        -------
        Instance of `NavItem`
        """
        if kind == 'pixel':
            py, px = coord
            yres = self.MapWidthHeight[1]
            py = yres - py
            stage_x, stage_y = self.pixel_to_stagecoords((px, py))
        else:
            stage_x, stage_y = coord

        d = {}
        try:
            d['BklshXY'] = self.BklshXY
        except AttributeError:
            d['BklshXY'] = 10, -10
        d['Color'] = 0
        d['DrawnID'] = self.MapID
        d['GroupID'] = MapItem.GROUP_ID_ITERATOR
        # d["MapID"] = 1 + self.i  # must be a unique ID under 100000 [optional, default=0]
        d['Acquire'] = int(acquire)
        d['NumPts'] = 1
        d['PtsX'] = [stage_x]
        d['PtsY'] = [stage_y]
        d['Regis'] = self.Regis
        d['StageXYZ'] = [stage_x, stage_y, self.stage_z]
        d['Type'] = 0

        item = NavItem(d, tag=tag)

        self.markers[item.tag] = item

        return item

    def add_marker_group(self,
                         coords: list,
                         kind: str = 'pixel',
                         acquire: bool = True,
                         replace: bool = True,
                         ) -> list:
        """Add pixel coordinates (numpy) as markers to a map item If
        `replace==True`, replace the entire list of existing markers on this
        `MapItem` (via `.markers`).

        Parameters
        ----------
        coords : array (n x 2)
            List of X, Y pixel coordinates or stage coordinates corresponding to the navigation item.
        kind : str
            Defines the kind of coordinate supplied, must be one of `pixel` or `stage`. Stage coordinates
            are given in μm.
        acquire : bool
            Turn on the acquire flag for this item.
        replace : bool
            Replace the exisiting items on this instance of `MapItem`

        Returns
        -------
        List of `NavItem` instances
        """
        if replace:
            self.markers = {}

        ret = []
        for i, coord in enumerate(coords):
            tag = f'{self.tag}-{i}'
            item = self.add_marker(coord, kind=kind, tag=tag, acquire=True)
            ret.append(item)

        MapItem.GROUP_ID_ITERATOR += 1

        return ret

    def update_markers(self, *items):
        """Update the list of markers belonging to this `Map` with the given
        items."""
        for item in items:
            self.markers[item.tag] = item

    def set_markers(self, *items):
        """Replace the list of markers belonging to this `Map` with the given
        items."""
        self.markers = {}
        self.update_markers(*items)

    @classmethod
    def from_dict(cls, dct, tag: str = None):
        """Construct a new map item from a dictionary.

        For the required keys, see `serialem.REQUIRED_MAPITEM

        Parameters
        ----------
        dct : dict
            Dictionary of required items
        tag : str
            Name to identify the map item by

        Returns
        -------
        map_item : MapItem
        """
        MapID = MapItem.GROUP_ID_ITERATOR
        MapItem.GROUP_ID_ITERATOR += 1

        # required items that can be generated
        map_dct = {
            'Color': 2,
            'Regis': 1,
            'Type': 2,
            'MapID': MapID,
            'MapMontage': 0,
            'MapCamera': 0,
            'NumPts': 5,       # number of points describing square around it?
            'PtsX': (-1, 1, 1, -1, -1),  # draw square around point, grid coordinates
            'PtsY': (-1, -1, 1, 1, -1),  # draw square around point, grid coordinates
        }

        map_dct.update(dct)

        if not tag:
            tag = str(MapID)

        map_item = cls(map_dct, tag=tag)
        map_item.calculate_PtsXY()

        return map_item

    def validate(self) -> None:
        """Validate the dictionary.

        Check whether all necessary keys are present
        """
        for key in REQUIRED_MAPITEM:
            if key not in self.__dict__:
                raise KeyError(f'MapItem: missing key `{key}`')

    def calculate_PtsXY(self) -> None:
        """Calculate PtsX / PtsY from the `map_item` information
        (MapWidthHeight) via `.pixel_to_stagecoords`.

        Updates the internal values.
        """
        x, y = self.MapWidthHeight

        pts = np.array((
            (0, 0),
            (x, 0),
            (x, y),
            (0, y),
            (0, 0),
        ))

        coords = self.pixel_to_stagecoords(pts)

        PtsX, PtsY = coords.T
        self.PtsX = PtsX.tolist()
        self.PtsY = PtsY.tolist()


def block2dict(block: list, kind: str = None, sequence: int = -1) -> dict:
    """Takes a text block from a SerialEM .nav file and converts it into a
    dictionary."""
    patt_split = re.compile(r'\s?=\s?')
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
                print('Unknown item:', item)
        except Exception as e:
            print(e)
            print(item)
            print(key, value)
            raise

        d[key] = value

    if sequence >= 0:
        d['sequence'] = sequence
    if kind:
        d['kind'] = kind

    return d


def block2nav(block: list, tag=None) -> 'NavItem':
    """Takes a text block from a SerialEM .nav file and converts it into a
    instance of `NavItem` or `MapItem`"""
    d = block2dict(block)
    kind = d['Type']

    if kind == 2:
        ret = MapItem(d, tag=tag)
    else:
        ret = NavItem(d, tag=tag)

    return ret


def read_nav_file(fn: str, acquire_only: bool = False) -> list:
    """Reads a SerialEM .nav file and returns a list of dictionaries containing
    nav item data.

    acquire_only: bool
        read only files with the Acquire tag set
    """

    # https://regex101.com/
    patt_match = re.compile(r'\[Item\s?=\s?([a-zA-Z0-9_-]*)\]')

    capture = False
    block = []
    items = []
    tag = ''

    f = open(fn, 'r')
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
            if line.startswith('AdocVersion'):
                pass
            elif line.startswith('LastSavedAs'):
                pass
            else:
                print(line)

    items.append(block2nav(block, tag=tag))

    if acquire_only:
        items = [item for item in items if item.Acquire]

    # associate markers with map items
    map_items = (item for item in items if item.kind == 'Map')
    markers = (item for item in items if item.kind == 'Marker')

    d = defaultdict(list)

    for marker in markers:
        d[marker.DrawnID].append(marker)

    for map_item in map_items:
        markers = d[map_item.MapID]
        map_item.update_markers(*markers)

    return items


def write_nav_file(fn: str, *items, mode='w') -> None:
    """Write list of nav items to a navigator file with filename `fn` to be
    read by SerialEM.

    `items` must be a list of NavItem / MapItem objects

    mode can be "w" to write a new file, or "a" to append
    items to an existing file
    """
    f = open(fn, mode) if fn else None
    version = '2.00'

    if mode == 'w':
        print(f'AdocVersion = {version}', file=f)
        print(f'LastSavedAs = {fn}', file=f)
        print('', file=f)

    for item in items:
        print(item.to_string(), file=f)


def read_mdoc_file(fn: str, only_kind: str = None) -> list:
    """Reads a SerialEM .mdoc file and returns a list of dictionaries
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
    patt_match = re.compile(r'\[([a-zA-Z]+)\s?=\s?([0-9]+)\]')

    capture = False
    block = []
    items = []
    kind = None
    sequence = 0

    f = open(fn, 'r')
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
        items = [item for item in items if item['kind'].lower() == only_kind]

    return items


if __name__ == '__main__':
    fn = 'C:/s/work_2019-06-26/navs2.nav'
    items = read_nav_file(fn)

    from IPython import embed
    embed()
