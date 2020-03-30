"""This JOBS repository holds a list of jobs that are useful outside the
function they were originally written for.

Should be generally applicable.
"""
import time
from datetime import datetime

from instamatic.formats import read_tiff
from instamatic.formats import write_tiff


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


def save_image(controller, **kwargs):
    frame = kwargs.get('frame')

    module_io = controller.app.get_module('io')

    drc = module_io.get_experiment_directory()
    drc.mkdir(exist_ok=True, parents=True)

    timestamp = datetime.now().strftime('%H-%M-%S.%f')[:-3]  # cut last 3 digits for ms resolution
    outfile = drc / f'frame_{timestamp}.tiff'

    try:
        flatfield, h = read_tiff(module_io.get_flatfield())
        frame = apply_flatfield_correction(frame, flatfield)
    except BaseException:
        frame = frame
        h = {}

    write_tiff(outfile, frame, header=h)
    print('Wrote file:', outfile)


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
    'save_image': save_image,
    'toggle_difffocus': toggle_difffocus,
    'relax_beam': relax_beam,

}
