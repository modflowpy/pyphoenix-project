from typing import Optional

import numpy as np
from attr import define, field
from numpy.typing import NDArray

from flopy4 import component, init_tree, resolve_array, setattribute
from flopy4.mf6 import Package


@component
@define(init=False, slots=False, on_setattr=setattribute)
class Dis(Package):
    length_units: str = field(
        # store block as metadata then dynamically
        # discover and expose blocks as properties.
        default=None,
        metadata={"block": "options"},
        # OR, blocks could be attrs classes too...
        # that will be necessary if variable names
        # at the top level are not unique, but they
        # currently are (if we like that constraint
        # we should document it and enforce it when
        # DFNs are loaded?)
    )
    nogrb: bool = field(default=False, metadata={"block": "options"})
    xorigin: float = field(default=None, metadata={"block": "options"})
    yorigin: float = field(default=None, metadata={"block": "options"})
    angrot: float = field(default=None, metadata={"block": "options"})
    export_array_netcdf: bool = field(
        default=False, metadata={"block": "options"}
    )
    nlay: int = field(default=1, metadata={"block": "dimensions"})
    ncol: int = field(default=2, metadata={"block": "dimensions"})
    nrow: int = field(default=2, metadata={"block": "dimensions"})
    delr: NDArray[np.floating] = field(
        # we use a converter both to resolve an array shape
        # and check it, handling both conversion/validation
        converter=resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(ncol,)"},
    )
    delc: NDArray[np.floating] = field(
        converter=resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(nrow,)"},
    )
    top: NDArray[np.floating] = field(
        converter=resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(ncol, nrow)"},
    )
    botm: NDArray[np.floating] = field(
        converter=resolve_array,
        default=0.0,
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"},
    )
    idomain: Optional[NDArray[np.integer]] = field(
        converter=resolve_array,
        default=1,
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"},
    )
    nodes: Optional[int] = field(default=None)

    def __init__(
        self=None,
        model=None,
        name=None,
        path=None,
        length_units=None,
        nogrb=False,
        xorigin=None,
        yorigin=None,
        angrot=None,
        export_array_netcdf=False,
        nlay=1,
        ncol=2,
        nrow=2,
        delr=1.0,
        delc=1.0,
        top=1.0,
        botm=0.0,
        idomain=1,
    ):
        super().__init__(name, path)
        init_tree(
            self,
            parent=model,
            length_units=length_units,
            nogrb=nogrb,
            xorigin=xorigin,
            yorigin=yorigin,
            angrot=angrot,
            export_array_netcdf=export_array_netcdf,
            nlay=nlay,
            ncol=ncol,
            nrow=nrow,
            nodes=ncol * nrow * nlay,
            delr=delr,
            delc=delc,
            top=top,
            botm=botm,
            idomain=idomain,
        )
