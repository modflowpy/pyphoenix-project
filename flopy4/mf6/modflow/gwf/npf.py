from pathlib import Path
from typing import Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converters import dict_to_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
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

    save_flows: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    alternative_cell_averaging: Optional[str] = field(block="options", default=None)
    thickstrt: bool = field(block="options", default=False)
    cvoptions: Optional[CvOptions] = field(block="options", default=None)
    perched: bool = field(block="options", default=False)
    rewet_record: Optional[RewetRecord] = field(block="options", default=None)
    xt3d_options: Optional[Xt3dOptions] = field(block="options", default=None)
    save_specific_discharge: bool = field(block="options", default=None)
    save_saturation: bool = field(block="options", default=None)
    k22overk: bool = field(block="options", default=None)
    k33overk: bool = field(block="options", default=None)
    tvk_filerecord: Optional[Path] = field(block="options", default=None)
    export_array_ascii: bool = field(block="options", default=False)
    export_array_netcdf: bool = field(block="options", default=False)
    dev_no_newton: bool = field(block="options", default=False)
    dev_omega: Optional[float] = field(block="options", default=None)
    icelltype: NDArray[np.integer] = array(
        block="griddata",
        dims=("nnodes",),
        default=0,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    k: NDArray[np.float64] = array(
        block="griddata",
        dims=("nnodes",),
        default=1.0,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    k22: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nnodes",),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    k33: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nnodes",),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    angle1: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nnodes",),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    angle2: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nnodes",),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    angle3: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nnodes",),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    wetdry: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nnodes",),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
