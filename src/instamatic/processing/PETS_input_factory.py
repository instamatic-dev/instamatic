from __future__ import annotations

import dataclasses
import time
from copy import deepcopy
from io import StringIO
from pathlib import Path
from string import punctuation
from textwrap import dedent
from typing import Any, Iterable, Optional, Union
from warnings import warn

import numpy as np
import pandas as pd
from typing_extensions import Self

from instamatic import config
from instamatic._collections import partial_formatter
from instamatic._typing import AnyPath

pets_input_keywords_csv = """
field,end
autotask,true
keepautotasks,false
lambda,false
aperpixel,false
geometry,false
detector,false
noiseparameters,false
phi,false
omega,false
delta,false
pixelsize,false
bin,false
reflectionsize,false
dstarmax,false
dstarmaxps,false
dstarmin,false
centerradius,false
beamstop,optional
badpixels,true
avoidicerings,false
icerings,true
peaksearchmode,false
center,false
centermode,false
i/sigma,false
mask,true
moreaveprofiles,false
peakprofileparams,false
peakprofilesectors,false
background,false
backgroundmethod,false
peakanalysis,false
minclusterpoints,false
indexingmode,false
indexingparameters,false
maxindex,false
cellrefinemode,false
cellrefineparameters,false
referencecell,false
intensitymethod,false
adjustreflbox,false
resshellfraction,false
saturationlimit,false
skipsaturated,false
minrotaxisdist,false
minreflpartiality,false
rcshape,false
integrationmode,false
integrationparams,false
intkinematical,false
intdynamical,false
dynamicalscales,false
dynamicalerrormodel,false
errormodel,false
outliers,false
refinecamelparams,false
orientationparams,false
simulationpower,false
interpolationparams,false
distcenterasoffset,false
distortunits,false
distortions,true
distortionskeys,true
mapformat,false
reconstruction,true
reconstructionparams,false
removebackground,false
serialed,false
virtualframes,false
cifentries,true
imagelist,true
celllist,true
cellitem,true
"""


class PetsKeywords:
    """Read PETS2 field metadata as read from the PETS2 manual."""

    def __init__(self, table: pd.DataFrame) -> None:
        table.fillna({'end': 'optional'}, inplace=True)
        self.table = table

    @classmethod
    def from_string(cls, string: str) -> Self:
        return cls(pd.read_csv(StringIO(string), index_col='field'))

    @classmethod
    def from_file(cls, path: AnyPath) -> Self:
        return cls(pd.read_csv(Path(path), index_col='field'))

    @property
    def list(self) -> np.ndarray[str]:
        return self.table.index.values

    def find(self, text: str) -> set[str]:
        first_words = set(
            line.strip().split()[0].strip(punctuation).lower()
            for line in text.splitlines()
            if line.strip()
        )
        return first_words.intersection(self.list)


pets_keywords = PetsKeywords.from_string(pets_input_keywords_csv)


@dataclasses.dataclass
class PetsInputElement:
    """Store metadata for a single PETS input element."""

    keywords: list[str]
    values: list[any]
    string: Optional[str] = None

    def __str__(self):
        return self.string if self.string is not None else self.build_string()

    @classmethod
    def from_any(cls, keyword_or_text: str, values: Optional[list[Any]] = None) -> Self:
        keywords = pets_keywords.find(keyword_or_text)
        if len(keywords) == 1 and values is not None:  # a single keyword with some values
            return cls([keywords.pop()], values)
        else:  # any other text block
            return cls(keywords=list(keywords), values=[], string=keyword_or_text)

    def has_end(self):
        return (
            len(self.keywords) == 1
            and self.keywords[0] in pets_keywords.list
            and pets_keywords.table.at[self.keywords[0], 'end'] != 'false'
        )

    def build_string(self):
        assert len(self.keywords) == 1
        prefix = [self.keywords[0]]
        delimiter = '\n' if self.has_end() else ' '
        suffix = [f'end{self.keywords[0]}'] if self.has_end() else []
        return delimiter.join(str(s) for s in prefix + self.values + suffix)


AnyPetsInputElement = Union[PetsInputElement, str]


class PetsInputWarning(UserWarning):
    pass


class PetsInputFactory:
    """Compile a PETS / PETS2 input file while preventing duplicates.

    This class is a general replacement for a simple print-to-file mechanism
    used previously. Using a list of all PETS2-viable keywords, it parses
    input strings and remembers all added commands. In addition to hard-coded
    parameters, it includes `config.camera.pets_prefix` (at the beginning)
    and `config.camera.pets_suffix` (at the end of the file). When a duplicate
    `PetsInputElement` is to be added, it is ignored and a warning is raised.
    """

    def __init__(self, elements: Optional[Iterable[AnyPetsInputElement]] = None) -> None:
        """As the input is built as we add, store current string & keywords."""
        self.current_elements: list[PetsInputElement] = []
        self.current_keywords: list[str] = []
        if elements is not None:
            for element in elements:
                self.add(element)

    def __add__(self, other: Self) -> Self:
        new = deepcopy(self)
        for element in other.current_elements:
            new.add(element)
        return new

    def __str__(self) -> str:
        return '\n'.join(str(e) for e in self.current_elements)

    def add(self, element: AnyPetsInputElement, *values: Any) -> None:
        """Add a PETS kw/values, a '# comment', or a text to be parsed."""
        if values or not isinstance(element, PetsInputElement):
            element = PetsInputElement.from_any(element, list(values))
        if self._no_duplicates_in(element.keywords):
            self.current_elements.append(element)

    def compile(self, image_converter_attributes: dict) -> Self:
        """Build a full version of PETS input with title, prefix, suffix."""
        title = dedent(f"""
        # PETS input file for Electron Diffraction generated by `instamatic`
        # {str(time.ctime())}
        # For definitions of input parameters, see: https://pets.fzu.cz/
        """).strip()

        prefix = getattr(config.camera, 'pets_prefix', None)
        if prefix is not None and image_converter_attributes is not None:
            prefix = partial_formatter.format(prefix, **image_converter_attributes)
        prefix = PetsInputElement.from_any(prefix)

        suffix = getattr(config.camera, 'pets_suffix', None)
        if suffix is not None and image_converter_attributes is not None:
            suffix = partial_formatter.format(suffix, **image_converter_attributes)
        suffix = PetsInputElement.from_any(suffix)

        return self.__class__([title, prefix] + self.current_elements + [suffix])

    def _no_duplicates_in(self, keywords: Iterable[str]) -> bool:
        """Return True & add keywords if there are no duplicates; else warn."""
        no_duplicates = True
        for keyword in keywords:
            if keyword in self.current_keywords:
                warn(f'Duplicate keyword rejected: {keyword}', PetsInputWarning)
                no_duplicates = False
        if no_duplicates:
            self.current_keywords.extend(list(keywords))
        return no_duplicates


if __name__ == '__main__':
    # test: find which keywords are added from prefix and suffix only
    pif = PetsInputFactory().compile({})
    print('PETS DEFAULT INPUT (`config.camera.pets_prefix` + `suffix`:')
    print('---')
    print(str(pif), end='')
    print('---')
    print(f'FOUND KEYWORDS: {{{", ".join(pif.current_keywords)}}}')
