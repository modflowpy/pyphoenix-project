from pathlib import Path
from typing import Optional

from flopy.discretization.structuredgrid import StructuredGrid
from flopy.discretization.vertexgrid import VertexGrid
from xattree import xattree

from flopy4.mf6.gwe.adv import Adv
from flopy4.mf6.gwe.cnd import Cnd
from flopy4.mf6.gwe.ctp import Ctp
from flopy4.mf6.gwe.dis import Dis
from flopy4.mf6.gwe.disv import Disv
from flopy4.mf6.gwe.esl import Esl
from flopy4.mf6.gwe.est import Est
from flopy4.mf6.gwe.ic import Ic
from flopy4.mf6.gwe.lke import Lke
from flopy4.mf6.gwe.mve import Mve
from flopy4.mf6.gwe.oc import Oc
from flopy4.mf6.gwe.ssm import Ssm
from flopy4.mf6.gwf.disbase import DisBase
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
    "Gwe",
    "Dis",
    "Disv",
    "Adv",
    "Cnd",
    "Ctp",
    "Esl",
    "Est",
    "Ic",
    "Lke",
    "Mve",
    "Oc",
    "Ssm",
]


@xattree
class Gwe(Model):
    list_: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    dependent_variable_scaling: bool = field(block="options", default=False)
    netcdf_mesh2d_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    netcdf_structured_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    netcdf_input_file: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    dis: DisBase | None = field(converter=convert_grid, block="packages", default=None)
    ic: Ic | None = field(block="packages", default=None)
    oc: Oc | None = field(block="packages", default=None)
    adv: Adv | None = field(block="packages", default=None)
    cnd: Cnd | None = field(block="packages", default=None)
    est: Est | None = field(block="packages", default=None)
    ctp: list[Ctp] = field(block="packages")
    esl: list[Esl] = field(block="packages")
    lke: list[Lke] = field(block="packages")
    ssm: Ssm | None = field(block="packages", default=None)
    mve: Mve | None = field(block="packages", default=None)

    @property
    def grid(self):
        if self.dis is not None:
            return self.dis.to_grid()
