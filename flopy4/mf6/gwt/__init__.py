from pathlib import Path
from typing import ClassVar, Optional

from flopy.discretization.structuredgrid import StructuredGrid
from flopy.discretization.vertexgrid import VertexGrid
from xattree import xattree

from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.gwt.adv import Adv
from flopy4.mf6.gwt.api import Api
from flopy4.mf6.gwt.cnc import Cnc
from flopy4.mf6.gwt.dis import Dis
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
from flopy4.mf6.spec import xattree_field as field
from flopy4.mf6.spec import xattree_path as path
from flopy4.utils import to_path


def convert_grid(value):
    if isinstance(value, StructuredGrid):
        return Dis.from_grid(value)
    if isinstance(value, VertexGrid):
        return Disv.from_grid(value)
    if isinstance(value, (Dis, Disv)) or value is None:
        return value
    raise TypeError(f"Expected Grid or Dis/Disv, got {type(value)}")


__all__ = [
    "Gwt",
    "Dis",
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


@xattree
class Gwt(Model):
    dfn_name: ClassVar[str] = "gwt-nam"

    list_: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    dependent_variable_scaling: bool = field(block="options", default=False)
    netcdf_mesh2d_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, direction="out"
    )
    netcdf_structured_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, direction="out"
    )
    netcdf_input_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, direction="in"
    )
    dis: DisBase | None = field(converter=convert_grid, block="packages", default=None)
    ic: Ic | None = field(block="packages", default=None)
    oc: Oc | None = field(block="packages", default=None)
    adv: Adv | None = field(block="packages", default=None)
    dsp: Dsp | None = field(block="packages", default=None)
    mst: Mst | None = field(block="packages", default=None)
    cnc: list[Cnc] = field(block="packages")
    src: list[Src] = field(block="packages")
    lkt: list[Lkt] = field(block="packages")
    ssm: Ssm | None = field(block="packages", default=None)
    mvt: Mvt | None = field(block="packages", default=None)
    api: Api | None = field(block="packages", default=None)

    @property
    def grid(self):
        if self.dis is not None:
            return self.dis.to_grid()
