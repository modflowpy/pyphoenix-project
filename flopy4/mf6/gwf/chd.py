from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.constants import LENBOUNDNAME
from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, computed_field, field, path
from flopy4.mf6.utils.grid import update_maxbound
from flopy4.utils import to_path


@xattree
class Chd(Package):
    multi_package: ClassVar[bool] = True

    # Computed field for maxbound - uses attrs.field directly (not xattree)
    # so it appears in DFN but is not managed by xattree's data store.
    # Updated by update_maxbound() in post-init and when period arrays change.
    # xattree may reset this to None when tree structure changes, so we
    # recompute it in write() before serialization.
    maxbound: Optional[int] = computed_field(
        default=None,
        init=False,
        block="dimensions",
        longname="maximum number of constant heads",
    )

    def write(self, format=None, context=None):
        """Write the component, ensuring maxbound is current before serialization."""
        # Recompute maxbound in case xattree reset it when tree structure changed.
        # TODO: This workaround won't be needed after migrating to Pydantic, which
        # has native support for computed fields via @computed_field decorator.
        update_maxbound(self, None, None)
        super().write(format=format, context=context)

    auxiliary: Optional[list[str]] = array(
        block="options", default=None, longname="keyword to specify aux variables"
    )
    auxmultname: Optional[str] = field(
        block="options",
        default=None,
        longname="name of auxiliary variable for multiplier",
    )
    boundnames: bool = field(block="options", default=False)
    print_input: bool = field(
        block="options", default=False, longname="print input to listing file"
    )
    print_flows: bool = field(
        block="options", default=False, longname="print CHD flows to listing file"
    )
    save_flows: bool = field(
        block="options", default=False, longname="save CHD flows to budget file"
    )
    ts_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    obs_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    dev_no_newton: bool = field(
        default=False, block="options", longname="turn off Newton for unconfined cells"
    )
    head: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="head value assigned to constant head",
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="auxiliary variables",
    )
    boundname: Optional[NDArray[np.str_]] = array(
        dtype=f"<U{LENBOUNDNAME}",
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="constant head boundary name",
    )
