from typing import Optional

from xattree import xattree

from flopy4.mf6.model import Model
from flopy4.mf6.prt.dis import Dis
from flopy4.mf6.prt.fmi import Fmi
from flopy4.mf6.prt.mip import Mip
from flopy4.mf6.prt.oc import Oc
from flopy4.mf6.prt.prp import Prp
from flopy4.mf6.spec import field

__all__ = [
    "Prt",
    "Dis",
    "Fmi",
    "Mip",
    "Oc",
    "Prp",
]


@xattree
class Prt(Model):
    list_: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    dis: Dis | None = field(block="packages", default=None)
    fmi: Fmi | None = field(block="packages", default=None)
    mip: Mip | None = field(block="packages", default=None)
    oc: Oc | None = field(block="packages", default=None)
    prp: list[Prp] = field(block="packages")
