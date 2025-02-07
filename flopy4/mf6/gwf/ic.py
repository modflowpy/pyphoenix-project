import numpy as np
from attr import define, field
from numpy.typing import NDArray

from flopy4 import component, init_tree, resolve_array, setattribute
from flopy4.mf6 import Package


@component
@define(init=False, slots=False, on_setattr=setattribute)
class Ic(Package):
    strt: NDArray[np.floating] = field(
        converter=resolve_array,
        default=1.0,
        metadata={"block": "packagedata", "shape": "(nodes)"},
    )
    export_array_ascii: bool = field(
        default=False, metadata={"block": "options"}
    )
    export_array_netcdf: bool = field(
        default=False,
        metadata={"block": "options"},
    )

    def __init__(
        self,
        model=None,
        name=None,
        path=None,
        strt=1.0,
        export_array_ascii=False,
        export_array_netcdf=False,
    ):
        super().__init__(name, path)
        init_tree(
            self,
            parent=model,
            strt=strt,
            export_array_ascii=export_array_ascii,
            export_array_netcdf=export_array_netcdf,
        )
