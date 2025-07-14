from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter, setters
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.converters import dict_to_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


def _update_maxbound(instance, attribute, new_value):
    """Update maxbound when period block arrays change."""
    if hasattr(instance, '_updating_maxbound'):
        return new_value
    
    # Calculate maxbound from all relevant arrays
    maxbound_values = []
    
    # Check elev array
    elev_val = new_value if attribute and attribute.name == 'elev' else getattr(instance, 'elev', None)
    if elev_val is not None:
        elev = elev_val if elev_val.data.shape == elev_val.shape else elev_val.todense()
        maxbound_values.append(len(np.where(elev != FILL_DNODATA)[0]))
    
    # Check cond array
    cond_val = new_value if attribute and attribute.name == 'cond' else getattr(instance, 'cond', None)
    if cond_val is not None:
        cond = cond_val if cond_val.data.shape == cond_val.shape else cond_val.todense()
        maxbound_values.append(len(np.where(cond != FILL_DNODATA)[0]))
    
    # Check aux array  
    aux_val = new_value if attribute and attribute.name == 'aux' else getattr(instance, 'aux', None)
    if aux_val is not None:
        aux = aux_val if aux_val.data.shape == aux_val.shape else aux_val.todense()
        maxbound_values.append(len(np.where(aux != FILL_DNODATA)[0]))
    
    # Check boundname array
    boundname_val = new_value if attribute and attribute.name == 'boundname' else getattr(instance, 'boundname', None)
    if boundname_val is not None:
        boundname = boundname_val if boundname_val.data.shape == boundname_val.shape else boundname_val.todense()
        maxbound_values.append(len(np.where(boundname != "")[0]))
    
    # Update maxbound if we have values
    if maxbound_values:
        instance._updating_maxbound = True
        try:
            instance.maxbound = max(maxbound_values)
        finally:
            delattr(instance, '_updating_maxbound')
    
    return new_value


@xattree
class Drn(Package):
    multi_package: ClassVar[bool] = True
    auxiliary: Optional[list[str]] = array(block="options", default=None)
    auxmultname: Optional[str] = field(block="options", default=None)
    auxdepthname: Optional[str] = field(block="options", default=None)
    boundnames: bool = field(block="options", default=False)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    ts_filerecord: Optional[Path] = field(block="options", default=None)
    obs_filerecord: Optional[Path] = field(block="options", default=None)
    mover: bool = field(block="options", default=False)
    dev_cubic_scaling: bool = field(default=False, block="options")
    maxbound: Optional[int] = field(block="dimensions", default=None, init=False)
    elev: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=("nper", "nnodes"),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        on_setattr=_update_maxbound,
    )
    cond: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=("nper", "nnodes"),
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
        # Trigger maxbound calculation on initialization
        if self.elev is not None or self.cond is not None or self.aux is not None or self.boundname is not None:
            _update_maxbound(self, None, None)
