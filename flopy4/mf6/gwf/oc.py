from pathlib import Path
from typing import Literal, Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.codec import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field
from flopy4.utils import to_path


@xattree
class Oc(Package):
    @define(slots=False)
    class FormatRecord:
        columns: int = field(default=10)
        width: int = field(default=11)
        digits: int = field(default=4)
        format: Literal["exponential", "fixed", "general", "scientific"] = field(default="general")

    @define(slots=False)
    class OCSetting:
        first: bool = field(default=True)
        last: bool = field(default=False)
        all: bool = field(default=False)
        steps: Optional[tuple[int]] = field(default=None)
        frequency: Optional[int] = field(default=None)

    @define(slots=False)
    class SaveRecord:
        rtype: str = field()
        ocsetting: "Oc.OCSetting" = field()

    @define(slots=False)
    class PrintRecord:
        rtype: str = field()
        ocsetting: "Oc.OCSetting" = field()

    @define(slots=False)
    class PeriodData:
        saverecord: Optional[tuple["Oc.SaveRecord"]] = field(default=None)
        printrecord: Optional[tuple["Oc.PrintRecord"]] = field(default=None)

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
    headprintrecord: Optional[FormatRecord] = field(block="options", default=None, init=False)
    perioddata: Optional[NDArray[np.object_]] = array(
        PeriodData,
        block="period",
        default=None,
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )
