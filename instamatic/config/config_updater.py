from collections import defaultdict
from pathlib import Path

from .utils import yaml


def is_oldstyle(dct: dict):
    oldstyle = any('_' in key for key in dct.mapping.keys())
    return oldstyle


def convert_calibration(fn: str) -> dict:
    fn = Path(fn)

    dct = yaml.full_load(open(fn))

    new = defaultdict(dict)
    for k, v in dct.items():
        if '_' in k:
            k2, k1 = k.split('_')
            print(k1, k2)
            new[k1][k2] = v
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
