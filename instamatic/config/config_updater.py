import shutil
from collections import defaultdict
from pathlib import Path

from instamatic.config.utils import yaml


def is_oldstyle(dct: dict, kind: str):
    """Check if the config format has been deprecated."""
    oldstyle = False
    if kind in ('microscope', 'calibration'):
        oldstyle = any('_' in key for key in dct.mapping.keys())
    if kind in ('microscope', 'camera'):
        oldstyle = oldstyle or any('name' in key for key in dct.mapping.keys())
    return oldstyle


def check_settings_yaml(src: str, dst: str):
    """Check if `dst` exists, else rename `src` to `dst`."""
    if dst.exists():
        return True

    if src.exists():
        src.rename(dst)
        print(f'Moved {src}->{dst}')


def check_defaults_yaml(drc: str, fn: str, src_fn: str = None):
    """Check if `drc/fn` exists, else copy `fn` from local drc (copy `src_fn`
    if specified)."""
    dst = drc / fn

    if not dst.exists():
        if not src_fn:
            src_fn = fn
        src = Path(__file__).parent / src_fn
        shutil.copy(src, dst)
        print(f'Copying {src}->{dst}')


def convert_config(fn: str, kind: str) -> dict:
    """`kind` must be one of `microscope`/`camera`/`calibration`"""
    fn = Path(fn)

    dct = yaml.full_load(open(fn))

    new = defaultdict(dict)
    for k, v in dct.items():
        if (k == 'name') and (kind in ('microscope', 'camera')):
            new['interface'] = v
        elif '_' in k:
            if kind == 'microscope':
                k1, k2 = k.split('_')
                new['ranges'][k2] = v
            elif kind == 'calibration':
                k2, k1 = k.split('_')
                new[k1][k2] = v
            else:
                new[k] = v
        else:
            new[k] = v

    new = dict(new)

    fn = Path(fn)
    backup = fn.with_suffix('.yaml_backup')
    if backup.exists():
        raise OSError(f'File `{backup}` already exists.')
    fn.rename(backup)
    yaml.dump(new, open(fn, 'w'))

    print('Updated:', fn)

    return new


if __name__ == '__main__':

    class config:
        def __init__(self, fn):
            self.fn = fn
            self.mapping = yaml.full_load(open(fn, 'r'))
            self.name = self.fn.parent.name

        def update(self):
            convert_config(self.fn, kind=self.name)

        @property
        def is_oldstyle(self):
            return is_oldstyle(self, kind=self.name)

    fns = list(Path(__file__).parent.glob('*/*.yaml'))

    for fn in fns:
        c = config(fn)

        if c.name not in ('microscope', 'calibration', 'camera'):
            continue

        if c.is_oldstyle:
            c.update()
        else:
            print(f'OK: {c.fn}')
