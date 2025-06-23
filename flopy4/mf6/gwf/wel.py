from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from numpy.typing import NDArray
from xattree import dict_to_array_converter

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


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
        converter=dict_to_array_converter,
        reader="urword",
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=dict_to_array_converter,
        reader="urword",
    )
    boundname: Optional[NDArray[np.str_]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=dict_to_array_converter,
        reader="urword",
    )

    def __attrs_post_init__(self):
        # TODO set up on_setattr hooks for period block
        # arrays to update maxbound? for now do it here
        # in post init. but this only works when values
        # are set in the initializer, not when they are
        # set later.
        if self.q is None:
            maxq = 0
        else:
            q = self.q if self.q.data.shape == self.q.shape else self.q.todense()
            maxq = len(np.where(q != FILL_DNODATA))
        if self.aux is None:
            maxaux = 0
        else:
            aux = self.aux if self.aux.data.shape == self.aux.shape else self.aux.todense()
            maxaux = len(np.where(aux != FILL_DNODATA))
        if self.boundname is None:
            maxboundname = 0
        else:
            boundname = (
                self.boundname
                if self.boundname.data.shape == self.boundname.shape
                else self.boundname.todense()
            )
            maxboundname = len(np.where(boundname != ""))

        self.maxbound = max(maxq, maxaux, maxboundname)
