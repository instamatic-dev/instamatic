import tempfile
import threading
from unittest.mock import MagicMock


def test_cred(ctrl):
    """This one is difficult to test with threads and events."""
    from instamatic.experiments import cred

    stopEvent = threading.Event()
    stopEvent.set()

    tempdrc = tempfile.TemporaryDirectory()
    expdir = tempdrc.name

    logger = MagicMock()

    cexp = cred.experiment.Experiment(
        ctrl,
        path=expdir,
        stop_event=stopEvent,
        log=logger,
        mode='simulate',
    )
    cexp.start_collection()

    tempdrc.cleanup()


def test_cred_tvips(ctrl):
    from instamatic.experiments import cRED_tvips

    tempdrc = tempfile.TemporaryDirectory()
    expdir = tempdrc.name

    logger = MagicMock()

    ctrl.stage.a = 20
    target_angle = -20
    exposure = 0.1
    manual_control = False
    mode = 'diff'

    exp = cRED_tvips.Experiment(
        ctrl=ctrl,
        path=expdir,
        log=logger,
        mode=mode,
        track=None,
        exposure=exposure,
    )
    exp.get_ready()

    exp.start_collection(
        target_angle=target_angle,
        manual_control=manual_control,
    )

    tempdrc.cleanup()


def test_red(ctrl):
    from instamatic.experiments import RED

    tempdrc = tempfile.TemporaryDirectory()
    expdir = tempdrc.name

    logger = MagicMock()

    exposure_time = 0.01
    tilt_range = 5
    stepsize = 1.0

    red_exp = RED.Experiment(
        ctrl=ctrl,
        path=expdir,
        log=logger,
        flatfield=None,
    )

    for x in range(2):
        red_exp.start_collection(
            exposure_time=exposure_time,
            tilt_range=tilt_range,
            stepsize=stepsize,
        )

    red_exp.finalize()

    tempdrc.cleanup()
