from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.constants import LENBOUNDNAME
from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.mf6.utils.grid import update_maxbound
from flopy4.utils import to_path


@xattree
class Chd(Package):
    multi_package: ClassVar[bool] = True

    # NOTE: maxbound is implemented as a property rather than an attrs field
    # because fields with init=False get reset by xattree's data management.
    # When migrating to Pydantic, use @computed_field decorator instead, which
    # provides first-class support for computed fields in serialization.
    @property
    def maxbound(self) -> Optional[int]:
        """
        Maximum number of constant heads.

        Dynamically computed from period block arrays.
        """
        from attrs import fields

        from flopy4.mf6.constants import FILL_DNODATA

        period_arrays = []
        for f in fields(self.__class__):
            if (
                f.metadata
                and f.metadata.get("block") == "period"
                and f.metadata.get("xattree", {}).get("dims")
            ):
                period_arrays.append(f.name)

        if not period_arrays:
            return None

        maxbound_values = []
        for array_name in period_arrays:
            array_val = getattr(self, array_name, None)
            if array_val is not None:
                import sparse

                if isinstance(array_val.data, sparse.SparseArray):
                    array_data = array_val.data.todense()
                else:
                    array_data = np.asarray(array_val.data)

                if array_data.dtype.kind in ["U", "S"]:
                    non_default_count = len(np.where(array_data != "")[0])
                else:
                    non_default_count = len(np.where(array_data != FILL_DNODATA)[0])

                maxbound_values.append(non_default_count)

        return max(maxbound_values) if maxbound_values else None

    @maxbound.setter
    def maxbound(self, value: Optional[int]) -> None:
        """Setter for maxbound (no-op, value is computed dynamically)."""
        pass

    @classmethod
    def get_dfn(cls):
        """Override to add maxbound to DFN (since it's a property, not a field)."""
        from modflow_devtools.dfn import Field

        dfn = super().get_dfn()

        # Add maxbound to dimensions block
        maxbound_field = Field(
            name="maxbound",
            block="dimensions",
            type="integer",
            optional=True,
            longname="maximum number of constant heads",
        )

        if "dimensions" not in dfn.blocks:
            dfn.blocks["dimensions"] = {}
        dfn.blocks["dimensions"]["maxbound"] = maxbound_field

        return dfn

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
