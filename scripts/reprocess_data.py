from instamatic.processing import ImgConversion
from instamatic.formats import read_tiff
import glob, sys
from pathlib import Path
import numpy as np

try:
    filepat = sys.argv[1]
except IndexError:
    filepat = "tiff/*.tiff"

fns = glob.glob(filepat)
n = len(fns)
if n == 0:
    print(f"No files found matching `{filepat}`")
    exit()
else:
    print(n)

buffer = []

fn = "cRED_log.txt"

rotation_axis = -2.24  # add np.pi/2 for old files
acquisition_time = None

with open(fn, "r") as f:
    for line in f:
        if line.startswith("Camera length"):
            camera_length = float(line.split()[2])
        if line.startswith("Oscillation angle"):
            osc_angle = float(line.split()[2])
        if line.startswith("Starting angle"):
            start_angle = float(line.split()[2])
        if line.startswith("Ending angle"):
            end_angle = float(line.split()[2])
        if line.startswith("Rotation axis"):
            rotation_axis = float(line.split()[2])
        if line.startswith("Acquisition time"):
            acquisition_time = float(line.split()[2])
        if line.startswith("Exposure Time"):
            exposure_time = float(line.split()[2])

if not acquisition_time:
    acquisition_time = exposure_time + 0.015

print("camera_length:", camera_length)
print("Oscillation angle:", osc_angle)
print("Starting angle:", start_angle)
print("Ending angle:", end_angle)
print("Rotation axis:", rotation_axis)
print("Acquisition time:", acquisition_time)


def extract_image_number(s):
    p = Path(s)
    return int(p.stem.split("_")[-1])

for i, fn in enumerate(fns):
    j = extract_image_number(fn)
    img, h = read_tiff(fn)
    buffer.append((j, img, h))

img_conv = ImgConversion.ImgConversion(buffer=buffer, 
         camera_length=camera_length,
         osc_angle=osc_angle,
         start_angle=start_angle,
         end_angle=end_angle,
         rotation_axis=rotation_axis,
         acquisition_time=acquisition_time,
         flatfield=None)

# azimuth, amplitude = 83.37, 2.43  # add 90 to azimuth for old files
# img_conv.stretch_azimuth, img_conv.stretch_amplitude = azimuth, amplitude
print("Stretch amplitude", img_conv.stretch_amplitude)
print("Stretch azimuth", img_conv.stretch_azimuth)

tiff_path = None
mrc_path = None
smv_path = None

# mrc_path = Path("reprocess")
smv_path = Path("SMV_reprocessed")

img_conv.threadpoolwriter(tiff_path=tiff_path,
                          mrc_path=mrc_path,
                          smv_path=smv_path,
                          workers=8)

if mrc_path:
    img_conv.write_ed3d(mrc_path)

if smv_path:
    img_conv.write_xds_inp(smv_path)
    # img_conv.to_dials(smv_path, interval=image_interval_enabled)
