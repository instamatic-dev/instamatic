from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from instamatic.experiments import RED, cRED, cRED_tvips, fast_adt
from instamatic.experiments.experiment_base import ExperimentBase
from tests.utils import InstanceAutoTracker


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


@dataclass
class ExperimentTestCase(InstanceAutoTracker):
    """Auto-registers experiment test case instances in INSTANCES."""

    cls: type[ExperimentBase]
    init_kwargs: dict[str, Any] = field(default_factory=dict)
    collect_kwargs: dict[str, Any] = field(default_factory=dict)
    num_collections: int = 1


ExperimentTestCase(
    cls=cRED.Experiment,
    init_kwargs={'stop_event': threading.Event(), 'mode': 'simulate'},
)

ExperimentTestCase(
    cls=cRED_tvips.Experiment,
    init_kwargs={'mode': 'diff', 'track': None, 'exposure': 0.1},
    collect_kwargs={'target_angle': -20, 'manual_control': False},
)

ExperimentTestCase(
    cls=RED.Experiment,
    init_kwargs={'flatfield': None},
    collect_kwargs={'exposure_time': 0.01, 'tilt_range': 5, 'stepsize': 1.0},
    num_collections=2,
)

fast_adt_common_collect_kwargs = {
    'diffraction_step': 0.5,
    'diffraction_time': 0.01,
    'tracking_algo': 'none',
    'tracking_time': 0.01,
}

ExperimentTestCase(
    cls=fast_adt.Experiment,
    collect_kwargs={
        'diffraction_mode': 'stills',
        'diffraction_start': -1,
        'diffraction_stop': 1,
        **fast_adt_common_collect_kwargs,
    },
)

ExperimentTestCase(
    cls=fast_adt.Experiment,
    collect_kwargs={
        'diffraction_mode': 'continuous',
        'diffraction_start': 1,
        'diffraction_stop': -1,
        **fast_adt_common_collect_kwargs,
    },
)


@pytest.mark.parametrize('test_case', ExperimentTestCase.INSTANCES)
def test_experiment(test_case: ExperimentTestCase, ctrl, tmp_path) -> None:
    test_case.init_kwargs['ctrl'] = ctrl
    test_case.init_kwargs['path'] = tmp_path
    test_case.init_kwargs['log'] = MagicMock()

    stop_event = test_case.init_kwargs.get('stop_event')
    if stop_event is not None:
        stop_event.set()

    with test_case.cls(**test_case.init_kwargs) as exp:
        for _ in range(test_case.num_collections):
            exp.start_collection(**test_case.collect_kwargs)
