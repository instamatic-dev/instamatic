import numpy as np
import yaml


def list_representer(dumper, data):
    """For cleaner printing of lists in yaml files."""
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)


def tuple_representer(dumper, data):
    """For cleaner printing of tuple in yaml files."""
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)


def array_representer(dumper, data):
    """For cleaner printing of arrays in yaml files."""
    out = data.tolist()
    if data.ndim <= 1:
        return dumper.represent_sequence('tag:yaml.org,2002:seq', out, flow_style=True)
    else:
        return dumper.represent_sequence('tag:yaml.org,2002:seq', out, flow_style=False)


representer = yaml.representer.Representer

representer.add_representer(list, list_representer)
representer.add_representer(tuple, tuple_representer)
representer.add_representer(np.ndarray, array_representer)

representer.add_representer(np.bool_, representer.represent_bool)
for np_type in [
    np.int_,
    np.intc,
    np.intp,
    np.int8,
    np.int16,
    np.int32,
    np.int64,
    np.uint8,
    np.uint16,
    np.uint32,
    np.uint64,
]:
    representer.add_representer(np_type, representer.represent_int)
for np_type in [
    np.float_,
    np.float16,
    np.float32,
    np.float64,
    np.longdouble,
]:
    representer.add_representer(np_type, representer.represent_float)
