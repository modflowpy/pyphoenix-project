from pathlib import Path
from typing import Literal, Optional

import attrs
import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array, structure_keyword
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.utils import to_path


@xattree
class Npf(Package):
    @define(slots=False)
    class CvOptions:
        variablecv: Literal["variablecv"] = attrs.field(init=False, default="variablecv")
        dewatered: Literal["dewatered"] | None = attrs.field(
            default=None,
            # TODO: adopt this pattern for all record types in all components?
            converter=Converter(structure_keyword, takes_field=True),  # type: ignore
        )

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
    tvk_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    export_array_ascii: bool = field(block="options", default=False)
    export_array_netcdf: bool = field(block="options", default=False)
    dev_no_newton: bool = field(block="options", default=False)
    dev_omega: Optional[float] = field(block="options", default=None)
    icelltype: NDArray[np.int64] = array(
        block="griddata",
        dims=("nodes",),
        default=0,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    k: NDArray[np.float64] = array(
        block="griddata",
        dims=("nodes",),
        default=1.0,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    k22: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nodes",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    k33: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nodes",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    angle1: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nodes",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    angle2: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nodes",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    angle3: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nodes",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    wetdry: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("nodes",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
