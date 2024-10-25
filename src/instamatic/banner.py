from __future__ import annotations

import instamatic


def thank_you_message(print_func=print, length: int = 70) -> None:
    import textwrap

    msg = f'Thank you for using {instamatic.__long_title__}. If you found this software useful, please consider citing it: {instamatic.__citation__}'

    h = '+' * length
    textwidth = length - 4
    lines = [line.ljust(textwidth) for line in textwrap.wrap(msg, width=textwidth)]
    lines = [f'+ {line} +' for line in lines]
    msg = '\n'.join(['', h, *lines, h, ''])

    print_func(msg)


def register_thank_you_message() -> None:
    import atexit

    atexit.register(thank_you_message)
