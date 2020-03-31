import json
import pickle

PROTOCOL = 'pickle'

# print(f"Protocol: `{PROTOCOL}`")


def json_loader(data):
    return json.loads(data.decode())


def json_dumper(data):
    return json.dumps(data).encode()


def pickle_loader(data):
    return pickle.loads(data)


def pickle_dumper(data):
    return pickle.dumps(data)


if PROTOCOL == 'json':
    loader = json_loader
    dumper = json_dumper
elif PROTOCOL == 'pickle':
    loader = pickle_loader
    dumper = pickle_dumper
else:
    raise ValueError(f'No such protocol: `{PROTOCOL}`')
