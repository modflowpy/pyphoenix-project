from pathlib import Path
from typing import Optional

import numpy as np
from attr import define, field
from numpy.typing import NDArray

from flopy4 import component, init_tree, resolve_array, setattribute
from flopy4.mf6 import Package


@component
@define(init=False, slots=False, on_setattr=setattribute)
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
        converter=resolve_array,
        default=0,
        metadata={"block": "griddata", "shape": ("nodes",)},
    )
    k: NDArray[np.floating] = field(
        converter=resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": ("nodes",)},
    )
    k22: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": ("nodes",)},
    )
    k33: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": ("nodes",)},
    )
    angle1: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": ("nodes",)},
    )
    angle2: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": ("nodes",)},
    )
    angle3: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": ("nodes",)},
    )
    wetdry: Optional[NDArray[np.floating]] = field(
        converter=resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": ("nodes",)},
    )

    def __init__(
        self,
        model=None,
        name=None,
        path=None,
        save_flows=False,
        print_flows=False,
        alternative_cell_averaging=None,
        thickstrt=False,
        cvoptions=None,
        perched=False,
        rewet_record=None,
        xt3doptions=None,
        save_specific_discharge=False,
        save_saturation=False,
        k22overk=False,
        k33overk=False,
        tvk_filerecord=None,
        export_array_ascii=False,
        export_array_netcdf=False,
        dev_no_newton=False,
        dev_omega=None,
        icelltype=0,
        k=1.0,
        k22=None,
        k33=None,
        angle1=None,
        angle2=None,
        angle3=None,
        wetdry=None,
    ):
        super().__init__(name, path)
        init_tree(
            self,
            parent=model,
            save_flows=save_flows,
            print_flows=print_flows,
            alternative_cell_averaging=alternative_cell_averaging,
            thickstrt=thickstrt,
            cvoptions=cvoptions,
            perched=perched,
            rewet_record=rewet_record,
            xt3doptions=xt3doptions,
            save_specific_discharge=save_specific_discharge,
            save_saturation=save_saturation,
            k22overk=k22overk,
            k33overk=k33overk,
            tvk_filerecord=tvk_filerecord,
            export_array_ascii=export_array_ascii,
            export_array_netcdf=export_array_netcdf,
            dev_no_newton=dev_no_newton,
            dev_omega=dev_omega,
            icelltype=icelltype,
            k=k,
            k22=k22,
            k33=k33,
            angle1=angle1,
            angle2=angle2,
            angle3=angle3,
            wetdry=wetdry,
        )
