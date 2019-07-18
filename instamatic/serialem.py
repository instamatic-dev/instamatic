from pathlib import Path
import re


# int
int_map = ("Color",        "NumPts",       "Draw",         "Regis", 
           "MapMontage",   "MapSection",   "MapBinning",   "MapMagInd", 
           "MapCamera",    "MapSettling",  "ShutterMode",  "MapSpotSize", 
           "MapSlitIn",    "MapSlitWidth", "ImageType",    "MontUseStage", 
           "MapProbeMode", "MapLDConSet",  "Type",         "GroupID",
           "MapID",        "PieceOn",      "Acquire",      "DrawnID",
           "MontBinning",  "SamePosId" )

# float
float_map = ("MapExposure", "MapIntensity", "MapTiltAngle")

# str
str_map = ("MapFile", "Note")

# list, float
list_float_map = ("StageXYZ", "RawStageXY", "MapScaleMat", "XYinPc",
                  "PtsX",     "PtsY",       "StageXYZ")

# list, int
list_int_map = ("BklshXY", "MapWidthHeight", "MapMinMaxScale", "MapFramesXY")

unknown_map = ()


class NavItem(object):
    """
    DataClass for SerialEM Nav items
    
    Type:
        0: Marker
        1: Polygon
        2: Map
    """
    def __init__(self, d: dict, tag: str):
        super().__init__()
        self._keys = tuple(d.keys())
        
        self.Acquire = 0
        self.__dict__.update(d)
        
        self.tag = tag

    def __repr__(self):
        return f"{self.__class__.__name__}({self.kind}[Item = {self.tag}])"

    @property
    def kind(self):
        return ("Marker", "Polygon", "Map")[self.Type]

    @property
    def stage_x(self):
        return self.StageXYZ[0]

    @property
    def stage_y(self):
        return self.StageXYZ[1]

    @property
    def stage_z(self):
        return self.StageXYZ[2]

    @property
    def map_scale_matrix(self):
        MapBinning = self.MapBinning
        MontBinning = self.MontBinning
        return (MapBinning / MontBinning) * np.array(self.MapScaleMat).reshape(2, 2)

    def to_string(self) -> str:
        """Convert nav item to string that can be printed to .nav file"""
        s = f"[Item = {self.tag}]\n"

        d = self.to_dict()

        for key in sorted(d.keys()):
            val = d[key]

            if key in int_map:
                val = str(val)
            elif key in float_map:
                val = str(val)
            elif key in list_float_map:
                val = " ".join([str(x) for x in val])
            elif key in list_int_map:
                val = " ".join([str(x) for x in val])

            s += f"{key} = {val}\n"

        s += ""

        return s

    def to_dict(self) -> dict:
        """Convert nav item back to dictionary"""
        return {key: self.__dict__[key] for key in self._keys}


def block2dict(block: list) -> dict:
    """Takes a text block from a SerialEM .nav file and converts it into a
    dictionary"""
    patt_split = re.compile("\s?=\s?")
    d = {}

    for item in block:
        key, value = re.split(patt_split, item)

        try:
            if key in int_map:
                value = int(value)
            elif key in float_map:
                value = float(value)
            elif key in str_map:
                value = str(value)
            elif key in list_float_map:
                value = [float(val) for val in value.split()]
            elif key in list_int_map:
                value = [int(val) for val in value.split()]
            elif key in unknown_map:
                print(item)
            else:
                print("Unknown item:", item)
        except Exception as e:
            print(e)
            print(item)
            print(key, value)
            breakpoint();exit()
            raise

        d[key] = value

    return d


def block2nav(block: list, tag=None) -> "NavItem":
    """Takes a text block from a SerialEM .nav file and converts it into a
    instance of `NavItem`"""
    return NavItem(block2dict(block), tag=tag)


def read_nav_file(fn: str) -> list:
    """
    Reads a SerialEM .nav file and returns a list of dictionaries
    containing nav item data.
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
            print(line)

    return items


if __name__ == '__main__':
    fn = "C:/s/work_2019-06-26/navs2.nav"
    items = read_nav_file(fn)

    breakpoint()