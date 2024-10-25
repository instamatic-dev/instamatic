from __future__ import annotations

import subprocess as sp
from pathlib import Path

import toml


def parse_lines(lines):
    ret = []

    buffer = []
    val = ''
    key = ''

    for line in lines:
        line = line.strip()

        if not line:
            break

        inp = line.split('  ', maxsplit=1)

        def flush():
            nonlocal val
            nonlocal key

            if val:
                buffer.append((key, val))
                val = ''

        if len(inp) == 2:
            flush()  # new key is found

            key = inp[0]
            val = inp[1].strip()

        elif inp[0].startswith('-'):
            flush()  # new key is found

            key = inp[0]
            try:
                val = inp[1].strip()
            except IndexError:
                pass

        else:
            val += ' ' + inp[0]

    flush()  # after loop

    for key, val in buffer:
        key_str = ', '.join(f'`{k.strip()}`' for k in key.split(','))
        ret.append(f'{key_str}:  \n{val}  ')

    return ret


out = open('autodoc.md', 'w')

fn = Path().absolute().parent / 'pyproject.toml'
print(fn)

d = toml.load(fn)
progs = d['tool']['poetry']['scripts']

category = '- **{}**'
toc = '  + [{}](#{}) (`{}`)'
header = '\n## {}\n'

capture = False
lines = []

for prog, loc in progs.items():
    ref = prog.replace('.', '')
    print(toc.format(prog, ref, loc), file=out)

for i, prog in enumerate(progs.keys()):
    positional = []
    optional = []
    description = []
    usage = []

    print(i, prog)
    print(header.format(prog), file=out)
    call = prog + '.exe' + ' -h'
    p = sp.run(call, capture_output=True)

    lines = iter(p.stdout.decode().splitlines())

    for line in lines:
        if line.startswith('Config directory:'):
            continue

        if line.startswith('usage:'):
            usage.append('**Usage:**  ')
            usage.append('```bash')
            usage.append(line[7:])
            for line in lines:
                if not line:
                    break
                usage.append(line[7:])
            usage.append('```')

        elif line.startswith('optional arguments:'):
            optional.append('**Optional arguments:**  ')

            new = parse_lines(lines)
            optional.extend(new)

        elif line.startswith('positional arguments:'):
            positional.append('**Positional arguments:**  ')

            new = parse_lines(lines)
            positional.extend(new)

        else:
            description.append(line)

    for line in description:
        print(line, file=out)

    for line in usage:
        print(line, file=out)

    for line in positional:
        print(line, file=out)

    if positional and optional:
        print('', file=out)

    for line in optional:
        print(line, file=out)

    print('', file=out)
