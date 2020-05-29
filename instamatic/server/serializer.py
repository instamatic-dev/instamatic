import json
import pickle

import yaml

from instamatic.config import settings
PROTOCOL = settings.tem_communication_protocol

# %timeit ctrl.stage.get()
# - pickle:  287 µs ± 10.7 µs per loop (mean ± std. dev. of 7 runs, 1000 loops each)
# - json:    320 µs ± 55.8 µs per loop (mean ± std. dev. of 7 runs, 1000 loops each)
# - msgpack: 512 µs ± 27.2 µs per loop (mean ± std. dev. of 7 runs, 1000 loops each)
# - yaml:   4.43 ms ± 13.7 µs per loop (mean ± std. dev. of 7 runs, 1000 loops each)


def json_loader(data):
    return json.loads(data.decode())


def json_dumper(data):
    return json.dumps(data).encode()


def yaml_loader(data):
    return yaml.safe_load(data.decode())


def yaml_dumper(data):
    return yaml.safe_dump(data).encode()


def pickle_loader(data):
    return pickle.loads(data)


def pickle_dumper(data):
    return pickle.dumps(data)


try:
    import msgpack
except ImportError:
    if PROTOCOL == 'msgpack':
        raise
else:
    def msgpack_loader(data):
        return msgpack.loads(data)

    def msgpack_dumper(data):
        return msgpack.dumps(data)


if PROTOCOL == 'json':
    loader = json_loader
    dumper = json_dumper
elif PROTOCOL == 'pickle':
    loader = pickle_loader
    dumper = pickle_dumper
elif PROTOCOL == 'yaml':
    loader = yaml_loader
    dumper = yaml_dumper
elif PROTOCOL == 'msgpack':
    loader = msgpack_loader
    dumper = msgpack_dumper
else:
    raise ValueError(f'No such protocol: `{PROTOCOL}`')
