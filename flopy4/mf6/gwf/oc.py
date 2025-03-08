from pathlib import Path
from typing import Literal, Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import array, field, xattree

from flopy4.mf6 import Package
from flopy4.mf6.converters import convert_array
from flopy4.utils import to_path


@xattree
class Oc(Package):
    @define(slots=False)
    class Format:
        columns: int = field(default=10)
        width: int = field(default=11)
        digits: int = field(default=4)
        format: Literal["exponential", "fixed", "general", "scientific"] = (
            field(default="general")
        )

    @define(slots=False)
    class Steps:
        all: bool = field()
        first: bool = field()
        last: bool = field()
        steps: list[int] = field()
        frequency: int = field()

    @define(slots=False)
    class Period:
        rtype: str = field()
        steps: "Oc.Steps" = field()

    budget_file: Optional[Path] = field(
        converter=to_path,
        default=None,
        metadata={"block": "options"},
    )
    budget_csv_file: Optional[Path] = field(
        converter=to_path,
        default=None,
        metadata={"block": "options"},
    )
    head_file: Optional[Path] = field(
        converter=to_path,
        default=None,
        metadata={"block": "options"},
    )
    format: Optional[Format] = field(
        default=None, init=False, metadata={"block": "options"}
    )
    saverecord: Optional[NDArray[np.object_]] = array(
        Period,
        dims=("per",),
        default=None,
        metadata={"block": "perioddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    printrecord: Optional[NDArray[np.object_]] = array(
        Period,
        dims=("per",),
        default=None,
        metadata={"block": "perioddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
