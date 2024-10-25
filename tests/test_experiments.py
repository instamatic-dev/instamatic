from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from instamatic.experiments import RED, cRED, cRED_tvips
from instamatic.experiments.experiment_base import ExperimentBase


def test_autoCRED(ctrl):
    from instamatic.experiments import autocRED

    assert issubclass(autocRED.Experiment, ExperimentBase)
    exp = autocRED.Experiment(ctrl, *[None] * 17, path=Path())
    pytest.xfail('Too complex to test at this point')


def test_serialED(ctrl):
    from instamatic.experiments import serialED

    assert issubclass(serialED.Experiment, ExperimentBase)
    with pytest.raises(OSError):
        exp = serialED.Experiment(ctrl, {})
    pytest.xfail('TODO')


@pytest.mark.parametrize(
    ['exp_cls', 'init_kwargs', 'collect_kwargs', 'num_collections'],
    [
        (
            cRED.Experiment,
            {
                'stop_event': threading.Event(),
                'mode': 'simulate',
            },
            {},
            1,
        ),
        (
            cRED_tvips.Experiment,
            {
                'mode': 'diff',
                'track': None,
                'exposure': 0.1,
            },
            {
                'target_angle': -20,
                'manual_control': False,
            },
            1,
        ),
        (
            RED.Experiment,
            {
                'flatfield': None,
            },
            {
                'exposure_time': 0.01,
                'tilt_range': 5,
                'stepsize': 1.0,
            },
            2,
        ),
    ],
)
def test_experiment(
    exp_cls: 'type[ExperimentBase]',
    init_kwargs: dict,
    collect_kwargs: dict,
    num_collections: int,
    ctrl,
    tmp_path,
):
    init_kwargs['ctrl'] = ctrl

    init_kwargs['path'] = tmp_path

    logger = MagicMock()
    init_kwargs['log'] = logger

    stop_event = init_kwargs.get('stop_event')
    if stop_event is not None:
        stop_event.set()

    with exp_cls(**init_kwargs) as exp:
        for _ in range(num_collections):
            exp.start_collection(**collect_kwargs)
