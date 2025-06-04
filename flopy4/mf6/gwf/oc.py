from pathlib import Path
from typing import Literal, Optional

import numpy as np
from attrs import Converter, define
from modflow_devtools.dfn import Field
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.codec import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field
from flopy4.utils import to_path

_OCSETTING = Field(
    name="ocsetting",
    type="keystring",
    reader="urword",
    children={
        "all": Field(
            name="all",
            type="keyword",
            reader="urword",
        ),
        "first": Field(
            name="first",
            type="keyword",
            reader="urword",
        ),
        "last": Field(
            name="last",
            type="keyword",
            reader="urword",
        ),
        "steps": Field(
            name="steps",
            type="integer",
            reader="urword",
        ),
        "frequency": Field(
            name="frequency",
            type="integer",
            reader="urword",
        ),
    },
)

_RTYPE = Field(
    name="rtype",
    type="string",
    reader="urword",
)


def _oc_action_field(action: str) -> Field:
    return Field(
        name=f"{action}record",
        type="recarray",
        dims=("nper",),
        block="perioddata",
        reader="urword",
        children={
            action: Field(
                name=action,
                type="keyword",
                reader="urword",
            ),
            "rtype": _RTYPE,
            "ocsetting": _OCSETTING,
        },
    )


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
        Steps,
        block="period",
        default="all",
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )
    save_budget: Optional[NDArray[np.object_]] = array(
        Steps,
        block="period",
        default="all",
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )
    print_head: Optional[NDArray[np.object_]] = array(
        Steps,
        block="period",
        default="all",
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )
    print_budget: Optional[NDArray[np.object_]] = array(
        Steps,
        block="period",
        default="all",
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )

    # original DFN
    # @classmethod
    # def get_dfn(cls) -> Dfn:
    #     """Generate the component's MODFLOW 6 definition."""
    #     dfn = super().get_dfn()
    #     for field_name in list(dfn["perioddata"].keys()):
    #         dfn["perioddata"].pop(field_name)
    #     dfn["perioddata"]["saverecord"] = _oc_action_field("save")
    #     dfn["perioddata"]["printrecord"] = _oc_action_field("print")
    #     return dfn
