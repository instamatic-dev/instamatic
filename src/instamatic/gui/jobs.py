"""This JOBS repository holds a list of jobs that are useful outside the
function they were originally written for.

Should be generally applicable.
"""

from __future__ import annotations

import time


def microscope_control(controller, **kwargs):
    from operator import attrgetter

    task = kwargs.pop('task')

    f = attrgetter(task)(controller.ctrl)  # nested getattr
    f(**kwargs)


def collect_flatfield(controller, **kwargs):
    from instamatic.processing import flatfield

    workdir = controller.module_io.get_working_directory()
    drc = workdir / 'flatfield'
    drc.mkdir(exist_ok=True, parents=True)

    flatfield.collect_flatfield(controller.ctrl, confirm=False, drc=drc, **kwargs)


def toggle_difffocus(controller, **kwargs):
    toggle = kwargs['toggle']

    if toggle:
        offset = kwargs['value']
        controller.ctrl.difffocus.defocus(offset=offset)
    else:
        controller.ctrl.difffocus.refocus()


def relax_beam(controller, **kwargs):
    n_cycles = 4
    print(f'Relaxing beam ({n_cycles} cycles)')

    controller.ctrl.mode.set('diff')

    offset = kwargs['value']

    for i in range(n_cycles):
        controller.ctrl.difffocus.defocus(offset=offset)
        time.sleep(0.25)
        controller.ctrl.difffocus.refocus()
        time.sleep(0.25)

    print('Done.')


JOBS = {
    'ctrl': microscope_control,
    'flatfield': collect_flatfield,
    'toggle_difffocus': toggle_difffocus,
    'relax_beam': relax_beam,
}
