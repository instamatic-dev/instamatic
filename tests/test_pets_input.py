from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Optional

import pytest

from instamatic.processing.PETS_input_factory import PetsInputFactory, PetsInputWarning


@dataclass
class PetsInputTestInfixCase:
    prefix: Optional[str]
    suffix: Optional[str]
    result: str
    warnings: tuple[type[UserWarning]] = ()


case0 = PetsInputTestInfixCase(  # tests if factory works in general
    prefix=None,
    suffix=None,
    result='# Title\ndetector asi\nreflectionsize 20',
)

case1 = PetsInputTestInfixCase(  # tests if prefix overwrites commands overwrites suffix
    prefix='detector default',
    suffix='reflectionsize 8',
    result='# Title\ndetector default\nreflectionsize 20',
    warnings=(PetsInputWarning,),
)

case2 = PetsInputTestInfixCase(  # tests if {format} fields are partially substituted
    prefix='detector {detector}\nreflectionsize {reflectionsize}',
    suffix=None,
    result='# Title\ndetector {detector}\nreflectionsize 9',
    warnings=(PetsInputWarning,),
)

case3 = PetsInputTestInfixCase(  # tests if partially-duplicate suffix is partially removed
    prefix=None,
    suffix='reflectionsize 8\nnoiseparameters 3.5 38',
    result='# Title\ndetector asi\nreflectionsize 20\nnoiseparameters 3.5 38',
    warnings=(PetsInputWarning,),
)

case4 = PetsInputTestInfixCase(  # tests the consistency of comment and empty line behavior
    prefix='# Prefix1\n\n# Prefix3\n\n',  # trailing \n cut
    suffix='',  # empty suffix ignored, so \n is not added
    result='# Title\n# Prefix1\n\n# Prefix3\n\ndetector asi\nreflectionsize 20',
)


@pytest.mark.parametrize('infix_case', [case0, case1, case2, case3, case4])
def test_pets_input(infix_case):
    pif = PetsInputFactory()

    # monkey patch PetsInputFactory class methods for the purpose of testing
    pif.get_title = lambda: '# Title'
    if (infix_case_prefix := infix_case.prefix) is not None:
        pif.get_prefix = lambda: infix_case_prefix
    if (infix_case_suffix := infix_case.suffix) is not None:
        pif.get_suffix = lambda: infix_case_suffix

    pif.add('detector', 'asi')
    pif.add('reflectionsize', 20)
    with pytest.warns(w) if (w := infix_case.warnings) else nullcontext():
        pif_compiled = pif.compile(dict(reflectionsize=9))
    assert str(pif_compiled) == infix_case.result
