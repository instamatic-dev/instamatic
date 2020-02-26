import yaml


def list_representer(dumper, data):
    """For cleaner printing of lists in yaml files."""
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)


yaml.representer.Representer.add_representer(list, list_representer)
