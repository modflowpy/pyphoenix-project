from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.converters import dict_to_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


def _update_maxbound(instance, attribute, new_value):
    """Update maxbound when period block arrays change."""
    if hasattr(instance, "_updating_maxbound"):
        return new_value

    # Calculate maxbound from all relevant arrays
    maxbound_values = []

    # Check q array
    q_val = new_value if attribute and attribute.name == "q" else getattr(instance, "q", None)
    if q_val is not None:
        q = q_val if q_val.data.shape == q_val.shape else q_val.todense()
        maxbound_values.append(len(np.where(q != FILL_DNODATA)[0]))

    # Check aux array
    aux_val = new_value if attribute and attribute.name == "aux" else getattr(instance, "aux", None)
    if aux_val is not None:
        aux = aux_val if aux_val.data.shape == aux_val.shape else aux_val.todense()
        maxbound_values.append(len(np.where(aux != FILL_DNODATA)[0]))

    # Check boundname array
    boundname_val = (
        new_value
        if attribute and attribute.name == "boundname"
        else getattr(instance, "boundname", None)
    )
    if boundname_val is not None:
        boundname = (
            boundname_val
            if boundname_val.data.shape == boundname_val.shape
            else boundname_val.todense()
        )
        maxbound_values.append(len(np.where(boundname != "")[0]))

    # Update maxbound if we have values
    if maxbound_values:
        instance._updating_maxbound = True
        try:
            instance.maxbound = max(maxbound_values)
        finally:
            delattr(instance, "_updating_maxbound")

    return new_value


@xattree
class Wel(Package):
    multi_package: ClassVar[bool] = True
    auxiliary: Optional[list[str]] = array(block="options", default=None)
    auxmultname: Optional[str] = field(block="options", default=None)
    boundnames: bool = field(block="options", default=False)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    auto_flow_reduce: float = field(block="options", default=None)
    afrcsv_filerecord: Optional[Path] = field(block="options", default=None)
    ts_filerecord: Optional[Path] = field(block="options", default=None)
    obs_filerecord: Optional[Path] = field(block="options", default=None)
    mover: bool = field(block="options", default=False)
    maxbound: Optional[int] = field(block="dimensions", default=None, init=False)
    q: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        on_setattr=_update_maxbound,
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        on_setattr=_update_maxbound,
    )
    boundname: Optional[NDArray[np.str_]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        on_setattr=_update_maxbound,
    )

    def __attrs_post_init__(self):
        if self.q is not None or self.aux is not None or self.boundname is not None:
            _update_maxbound(self, None, None)
