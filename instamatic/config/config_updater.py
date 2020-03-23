from collections import defaultdict
from pathlib import Path

from .utils import yaml


def is_oldstyle(dct: dict):
    oldstyle = any('_' in key for key in dct.mapping.keys())
    return oldstyle


def check_global_yaml(drc, old, new):
    old = Path(drc) / old
    new = Path(drc) / new

    print(old)
    print(new)

    if new.exists():
        return True

    if old.exists():
        old.rename(new)
        print(f'Moved {old}->{new}')


def convert_config(fn: str, kind: str) -> dict:
    """`kind` must be one of `microscope`/`camera`/`calibration`"""
    fn = Path(fn)

    dct = yaml.full_load(open(fn))

    new = defaultdict(dict)
    for k, v in dct.items():
        if '_' in k:
            if kind == 'microscope':
                k1, k2 = k.split('_')
                new['ranges'][k2] = v
            elif kind == 'calibration':
                k2, k1 = k.split('_')
                new[k1][k2] = v
            else:
                raise ValueError(f'Unrecognized value for `kind`: {kind}')
        else:
            new[k] = v

    new = dict(new)

    print('Updated:', fn)

    fn = Path(fn)
    backup = fn.with_suffix('.yaml_backup')
    if backup.exists():
        raise OSError(f'File `{backup}` already exists.')
    fn.rename(backup)
    yaml.dump(new, open(fn, 'w'))

    return new


if __name__ == '__main__':
    import sys
    for fn in sys.argv[1:]:
        convert_config(fn)
