from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.resources import files

from instamatic._collections import PartialFormatter

XDS_template_path = files('instamatic.processing').joinpath('XDS_template.inp')
XDS_template_base = XDS_template_path.read_text(encoding='utf-8')


@dataclass
class XDSPreset:
    max_cell_axis_error: str = '0.05'
    max_cell_angle_error: str = '3.0'
    strong_pixel_line: str = '!STRONG_PIXEL= 3.0'
    min_fraction_line: str = '!MINIMUM_FRACTION_OF_INDEXED_SPOTS= 0.25'


mce = {'max_cell_axis_error': '0.03', 'max_cell_angle_error': '2.0'}

xds_preset_base = XDSPreset()
xds_preset_dm = XDSPreset(min_fraction_line='MINIMUM_FRACTION_OF_INDEXED_SPOTS= 0.25 ', **mce)
xds_preset_tvips = XDSPreset(strong_pixel_line='STRONG_PIXEL= 6.0 ', **mce)

pf = PartialFormatter()
XDS_template = pf.format(XDS_template_base, **asdict(xds_preset_base))
XDS_template_DM = pf.format(XDS_template_base, **asdict(xds_preset_dm))
XDS_template_TPX = XDS_template
XDS_template_TVIPS = pf.format(XDS_template_base, **asdict(xds_preset_tvips))
