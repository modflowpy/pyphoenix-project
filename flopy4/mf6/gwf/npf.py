from pathlib import Path
from typing import Optional

import numpy as np
from attr import define, field
from numpy.typing import NDArray

from flopy4 import component, setattribute
from flopy4.mf6 import Package


@component(align=["nodes"])
@define(slots=False, on_setattr=setattribute)
class Npf(Package):
    @define(slots=False)
    class CvOptions:
        variablecv: bool = field(default=False)
        dewatered: bool = field(default=False)

    @define(slots=False)
    class RewetRecord:
        rewet: bool = field()
        wetfct: float = field()
        iwetit: int = field()
        ihdwet: int = field()

    @define(slots=False)
    class Xt3dOptions:
        xt3d: bool = field()
        rhs: bool = field()

    save_flows: bool = field(default=False, metadata={"block": "options"})
    print_flows: bool = field(default=False, metadata={"block": "options"})
    alternative_cell_averaging: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    thickstrt: bool = field(default=False, metadata={"block": "options"})
    cvoptions: Optional[CvOptions] = field(
        default=None, metadata={"block": "options"}
    )
    perched: bool = field(default=False, metadata={"block": "options"})
    rewet_record: Optional[RewetRecord] = field(
        default=None, metadata={"block": "options"}
    )
    xt3d_options: Optional[Xt3dOptions] = field(
        default=None, metadata={"block": "options"}
    )
    save_specific_discharge: bool = field(
        default=None, metadata={"block": "options"}
    )
    save_saturation: bool = field(default=None, metadata={"block": "options"})
    k22overk: bool = field(default=None, metadata={"block": "options"})
    k33overk: bool = field(default=None, metadata={"block": "options"})
    tvk_filerecord: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    export_array_ascii: bool = field(
        default=False, metadata={"block": "options"}
    )
    export_array_netcdf: bool = field(
        default=False, metadata={"block": "options"}
    )
    dev_no_newton: bool = field(default=False, metadata={"block": "options"})
    dev_omega: Optional[float] = field(
        default=None, metadata={"block": "options"}
    )
    icelltype: NDArray[np.integer] = field(
        default=0,
        metadata={"block": "griddata", "dims": ("nodes",)},
    )
    k: NDArray[np.floating] = field(
        default=1.0,
        metadata={"block": "griddata", "dims": ("nodes",)},
    )
    k22: Optional[NDArray[np.floating]] = field(
        default=None,
        metadata={"block": "griddata", "dims": ("nodes",)},
    )
    k33: Optional[NDArray[np.floating]] = field(
        default=None,
        metadata={"block": "griddata", "dims": ("nodes",)},
    )
    angle1: Optional[NDArray[np.floating]] = field(
        default=None,
        metadata={"block": "griddata", "dims": ("nodes",)},
    )
    angle2: Optional[NDArray[np.floating]] = field(
        default=None,
        metadata={"block": "griddata", "dims": ("nodes",)},
    )
    angle3: Optional[NDArray[np.floating]] = field(
        default=None,
        metadata={"block": "griddata", "dims": ("nodes",)},
    )
    wetdry: Optional[NDArray[np.floating]] = field(
        default=None,
        metadata={"block": "griddata", "dims": ("nodes",)},
    )
