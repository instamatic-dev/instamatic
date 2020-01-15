import io
from collections import OrderedDict

import pandas as pd
import yaml


def results2df(results, sort=True):
    """Convert a list of IndexingResult objects to pandas DataFrame."""
    import pandas as pd
    df = pd.DataFrame(results).T
    df.columns = list(results.values())[0]._fields
    if sort:
        df = df.sort_values('score', ascending=False)
    return df


def write_csv(f, results):
    """Write a list of IndexingResult objects to a csv file."""
    if not hasattr(results, 'to_csv'):
        results = results2df(results)
    results.to_csv(f)


def read_csv(f):
    """Read a csv file into a pandas DataFrame."""
    if isinstance(f, (list, tuple)):
        return pd.concat(read_csv(csv) for csv in f)
    else:
        return pd.DataFrame.from_csv(f)


def read_ycsv(f):
    """read file in ycsv format: https://blog.datacite.org/using-yaml-
    frontmatter-with-csv/

    format:
        ---
        $YAML_BLOCK
        ---
        $CSV_BLOCK
    """

    if isinstance(f, str):
        f = open(f, 'r')

    first_line = f.tell()

    in_yaml_block = False

    yaml_block = []

    for line in f:
        if line.strip() == '---':
            if not in_yaml_block:
                in_yaml_block = True
            else:
                in_yaml_block = False
                break
            continue

        if in_yaml_block:
            yaml_block.append(line)

    # white space is important when reading yaml
    d = yaml.load(io.StringIO(''.join(yaml_block)))

    # workaround to fix pandas crash when it is not at the first line for some reason
    f.seek(first_line)
    header = len(yaml_block) + 2
    try:
        df = pd.DataFrame.from_csv(f, header=header)
    except pd.io.common.EmptyDataError:
        df = None

    # print "".join(yaml_block)

    return df, d


def write_ycsv(f, data, metadata):
    """write file in ycsv format: https://blog.datacite.org/using-yaml-
    frontmatter-with-csv/

    format:
        ---
        $YAML_BLOCK
        ---
        $CSV_BLOCK
    """

    if isinstance(f, str):
        f = open(f, 'w')

    f.write('---\n')
    yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)

    f.write('---\n')
    write_csv(f, data)
