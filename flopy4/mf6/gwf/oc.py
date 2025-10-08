from pathlib import Path
from typing import Literal, Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import dict_to_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field
from flopy4.utils import to_path


@xattree
class Oc(Package):
    @define(slots=False)
    class Format:
        columns: int = field(default=10)
        width: int = field(default=11)
        digits: int = field(default=4)
        format: Literal["exponential", "fixed", "general", "scientific"] = field(default="general")

    @define(slots=False)
    class Steps:
        all: bool = field(default=True)
        first: bool | None = field(default=None)
        last: bool | None = field(default=None)
        steps: list[int] | None = field(default=None)
        frequency: int | None = field(default=None)

    @define(slots=False)
    class Period:
        rtype: str = field()
        steps: "Oc.Steps" = field()

    budget_file: Optional[Path] = field(
        block="options",
        converter=to_path,
        default=None,
    )
    budget_csv_file: Optional[Path] = field(
        block="options",
        converter=to_path,
        default=None,
    )
    head_file: Optional[Path] = field(
        block="options",
        converter=to_path,
        default=None,
    )
    format: Optional[Format] = field(block="options", default=None, init=False)
    save_head: Optional[NDArray[np.object_]] = array(
        object,
        block="period",
        default="all",
        dims=("nper",),
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        format="keystring",
    )
    save_budget: Optional[NDArray[np.object_]] = array(
        object,
        block="period",
        default="all",
        dims=("nper",),
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        format="keystring",
    )
    print_head: Optional[NDArray[np.object_]] = array(
        object,
        block="period",
        default="all",
        dims=("nper",),
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        format="keystring",
    )
    print_budget: Optional[NDArray[np.object_]] = array(
        object,
        block="period",
        default="all",
        dims=("nper",),
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        format="keystring",
    )
