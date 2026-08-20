from typing import ClassVar, Optional

from flopy.discretization.structuredgrid import StructuredGrid
from flopy.discretization.vertexgrid import VertexGrid
from xattree import xattree

from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.model import Model
from flopy4.mf6.prt.dis import Dis
from flopy4.mf6.prt.disv import Disv
from flopy4.mf6.prt.fmi import Fmi
from flopy4.mf6.prt.mip import Mip
from flopy4.mf6.prt.oc import Oc
from flopy4.mf6.prt.prp import Prp
from flopy4.mf6.spec import xattree_field as field


def convert_grid(value):
    if isinstance(value, StructuredGrid):
        return Dis.from_grid(value)
    if isinstance(value, VertexGrid):
        return Disv.from_grid(value)
    if isinstance(value, (Dis, Disv)) or value is None:
        return value
    raise TypeError(f"Expected Grid or Dis/Disv, got {type(value)}")


__all__ = [
    "Prt",
    "Dis",
    "Disv",
    "Fmi",
    "Mip",
    "Oc",
    "Prp",
]


@xattree
class Prt(Model):
    dfn_name: ClassVar[str] = "prt-nam"

    list_: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    dis: DisBase | None = field(converter=convert_grid, block="packages", default=None)
    fmi: Fmi | None = field(block="packages", default=None)
    mip: Mip | None = field(block="packages", default=None)
    oc: Oc | None = field(block="packages", default=None)
    prp: list[Prp] = field(block="packages")

    @property
    def grid(self):
        if self.dis is not None:
            return self.dis.to_grid()
