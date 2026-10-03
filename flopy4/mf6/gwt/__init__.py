from pathlib import Path
from typing import ClassVar, Optional

import attrs

from flopy4.mf6.gwt.adv import Adv
from flopy4.mf6.gwt.api import Api
from flopy4.mf6.gwt.cnc import Cnc
from flopy4.mf6.gwt.dis import Dis
from flopy4.mf6.gwt.disu import Disu
from flopy4.mf6.gwt.disv import Disv
from flopy4.mf6.gwt.dsp import Dsp
from flopy4.mf6.gwt.ic import Ic
from flopy4.mf6.gwt.lkt import Lkt
from flopy4.mf6.gwt.mst import Mst
from flopy4.mf6.gwt.mvt import Mvt
from flopy4.mf6.gwt.oc import Oc
from flopy4.mf6.gwt.src import Src
from flopy4.mf6.gwt.ssm import Ssm
from flopy4.mf6.model import Model
from flopy4.mf6.spec import child, field, path
from flopy4.utils import to_path

__all__ = [
    "Gwt",
    "Dis",
    "Disu",
    "Disv",
    "Adv",
    "Api",
    "Cnc",
    "Dsp",
    "Ic",
    "Lkt",
    "Mst",
    "Mvt",
    "Oc",
    "Src",
    "Ssm",
]


@attrs.define(kw_only=True, slots=False)
class Gwt(Model):
    dfn_name: ClassVar[str] = "gwt-nam"

    list_: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    dependent_variable_scaling: bool = field(block="options", default=False)
    netcdf_mesh2d_file: Optional[Path] = path(
        block="options",
        default=None,
        converter=to_path,
        direction="out",
        keyword="netcdf_mesh2d",
    )
    netcdf_structured_file: Optional[Path] = path(
        block="options",
        default=None,
        converter=to_path,
        direction="out",
        keyword="netcdf_structured",
    )
    netcdf_input_file: Optional[Path] = path(
        block="options",
        default=None,
        converter=to_path,
        direction="in",
        keyword="netcdf",
    )
    dis: Dis | Disv | Disu | None = child(block="packages")
    ic: Ic | None = child(block="packages")
    oc: Oc | None = child(block="packages")
    adv: Adv | None = child(block="packages")
    dsp: Dsp | None = child(block="packages")
    mst: Mst | None = child(block="packages")
    cnc: list[Cnc] = child(block="packages", default=attrs.Factory(list))
    src: list[Src] = child(block="packages", default=attrs.Factory(list))
    lkt: list[Lkt] = child(block="packages", default=attrs.Factory(list))
    ssm: Ssm | None = child(block="packages")
    mvt: Mvt | None = child(block="packages")
    api: Api | None = child(block="packages")

    @property
    def grid(self):
        if self.dis is not None:
            return self.dis.to_grid()
