from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Optional

import pytest

from instamatic.processing.PETS_input_factory import PetsInputFactory, PetsInputWarning
from tests.utils import InstanceAutoTracker


@dataclass(frozen=True)
class PetsInputTestInfixCase(InstanceAutoTracker):
    prefix: Optional[str]
    suffix: Optional[str]
    result: str
    warnings: tuple[type[UserWarning]] = ()


PetsInputTestInfixCase(  # tests if factory works in general
    prefix=None,
    suffix=None,
    result='# Title\ndetector asi\nreflectionsize 20',
)

PetsInputTestInfixCase(  # tests if prefix overwrites commands overwrites suffix
    prefix='detector default',
    suffix='reflectionsize 8',
    result='# Title\ndetector default\nreflectionsize 20',
    warnings=(PetsInputWarning,),
)

PetsInputTestInfixCase(  # tests if {format} fields are partially substituted
    prefix='detector {detector}\nreflectionsize {reflectionsize}',
    suffix=None,
    result='# Title\ndetector {detector}\nreflectionsize 9',
    warnings=(PetsInputWarning,),
)

PetsInputTestInfixCase(  # tests if partially-duplicate suffix is partially removed
    prefix=None,
    suffix='reflectionsize 8\nnoiseparameters 3.5 38',
    result='# Title\ndetector asi\nreflectionsize 20\nnoiseparameters 3.5 38',
    warnings=(PetsInputWarning,),
)

PetsInputTestInfixCase(  # tests the consistency of comment and empty line behavior
    prefix='# Prefix1\n\n# Prefix3\n\n',  # trailing \n cut
    suffix='',  # empty suffix ignored, so \n is not added
    result='# Title\n# Prefix1\n\n# Prefix3\n\ndetector asi\nreflectionsize 20',
)


@pytest.mark.parametrize('infix_case', PetsInputTestInfixCase.INSTANCES)
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
