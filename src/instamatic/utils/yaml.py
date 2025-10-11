from __future__ import annotations

import numpy as np
import yaml


def _numpy_2d_representer(dumper: yaml.Dumper, array: np.ndarray) -> yaml.nodes.SequenceNode:
    """Limit the number of newlines when writing numpy arrays where ndim>1."""
    data = array.tolist()

    if array.ndim == 1:
        node = dumper.represent_list(data)
        node.flow_style = True
    elif array.ndim >= 2:
        outer = []
        for row in data:
            inner = dumper.represent_list(row)
            inner.flow_style = True
            outer.append(inner)
        node = yaml.SequenceNode(tag='tag:yaml.org,2002:seq', value=outer, flow_style=False)
    else:
        node = dumper.represent_list(data)
    return node


class Numpy2DDumper(yaml.SafeDumper):
    """A yaml Dumper class that does not expand numpy arrays beyond 1st dim."""


Numpy2DDumper.add_representer(np.ndarray, _numpy_2d_representer)
