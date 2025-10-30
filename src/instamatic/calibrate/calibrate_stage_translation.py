from __future__ import annotations

import argparse
import logging
from time import perf_counter
from typing import NamedTuple, Optional, Sequence

import numpy as np
from skimage.registration import phase_cross_correlation
from tqdm import tqdm

from instamatic._typing import AnyPath, int_nm
from instamatic.config import camera
from instamatic.image_utils import autoscale, imgscale
from instamatic.microscope.utils import StagePositionTuple
from instamatic.utils.iterating import sawtooth

logger = logging.getLogger(__name__)


def log(s: str) -> None:
    logger.info(s)
    print(s)


class CalibStageTranslation: ...


class PCalibPoint(NamedTuple):
    """A single measurement point used to calib stage-camera transformation."""

    x: int_nm
    y: int_nm
    image: np.ndarray


class SCalibPoint(NamedTuple):
    """A single measurement point used to calibrate stage translation speed."""

    delta: int_nm
    speed: float
    time: float


def calibrate_stage_translation_live(
    ctrl: 'TEMController',
    xy_spans: Optional[Sequence[float]] = None,
    speed_range: Optional[Sequence[float]] = None,
    outdir: Optional[AnyPath] = None,
    plot: Optional[bool] = None,
) -> CalibStageTranslation:
    xy_spans = np.array(xy_spans or [10, 20, 30, 40, 50, 60, 70, 80])  # px
    alternating_ones = np.ones(len(xy_spans)) * (-1) ** np.arange(len(xy_spans))
    delta_dir = sawtooth(['x', 'y', 'x', 'y'])
    delta_span = np.repeat(xy_spans * alternating_ones, 2)

    stage0: StagePositionTuple = ctrl.stage.get()
    try:
        ctrl.stage.set_with_speed(*stage0)
    except KeyError:  # if stage cannot move with speed, investigate shifts only
        speed_range = [0]
    else:
        speed_range = speed_range or [0.1, 0.2, 0.3]
    finally:
        ctrl.stage.set(stage0.x, stage0.y, stage0.z, 0, 0)
    stage0 = ctrl.stage.get()
    image0, h0 = ctrl.get_image(header_keys=None)
    image0s, scale = autoscale(image0)

    p_calib_points: list[PCalibPoint] = []
    s_calib_points: list[SCalibPoint] = []
    ctrl.cam.block()
    try:
        n_calib_points = len(speed_range) * len(delta_span)
        log(f'Starting translation (speed) calibration based on {n_calib_points} points.')
        with tqdm(total=n_calib_points) as progress_bar:
            for speed in speed_range:
                setter = ctrl.stage.set_with_speed if speed > 0 else ctrl.stage.set
                setter_kw = {'speed': speed} if speed > 0 else {}

                ctrl.stage.set(*stage0)
                for d, s in zip(delta_dir, delta_span):
                    stage1 = ctrl.stage.get()
                    t1 = perf_counter()
                    setter(**{**{d: getattr(stage1, d) + s}, **setter_kw})
                    t2 = perf_counter()
                    stage2 = ctrl.stage.get()
                    img, h = ctrl.get_image(header_keys=None)
                    p_calib_points.append(PCalibPoint(x=stage2.x, y=stage2.y, image=img))
                    s_calib_points.append(SCalibPoint(delta=s, speed=speed, time=t2 - t1))
                    progress_bar.update(1)
    finally:
        ctrl.stage.set(*stage0)
        ctrl.cam.unblock()

    # Calibrate stage-camera transformation
    cam_deltas = []
    for p in p_calib_points:
        image_s = imgscale(p.image, scale)
        cam_deltas.append(phase_cross_correlation(image0s, image_s, upsample_factor=10)[0])

    binsize = h0['ImageBinsize']
    cam_deltas = np.array(cam_deltas) * binsize / scale
    stage_deltas = np.array([(s.x - stage0.x, s.y - stage1.y) for p in p_calib_points])
    # CalibStage.from_data(cam_deltas, stage_deltas)  TODO


if __name__ == '__main__':
    from instamatic import controller

    ctrl = controller.initialize()
    calibrate_stage_translation_live(ctrl=ctrl)
