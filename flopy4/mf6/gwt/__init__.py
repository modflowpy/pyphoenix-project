from typing import Optional

from xattree import xattree

from flopy4.mf6.gwt.adv import Adv
from flopy4.mf6.gwt.api import Api
from flopy4.mf6.gwt.cnc import Cnc
from flopy4.mf6.gwt.dis import Dis
from flopy4.mf6.gwt.dsp import Dsp
from flopy4.mf6.gwt.ic import Ic
from flopy4.mf6.gwt.mst import Mst
from flopy4.mf6.gwt.mvt import Mvt
from flopy4.mf6.gwt.src import Src
from flopy4.mf6.gwt.ssm import Ssm
from flopy4.mf6.model import Model
from flopy4.mf6.spec import field

__all__ = [
    "Gwt",
    "Dis",
    "Adv",
    "Api",
    "Cnc",
    "Dsp",
    "Ic",
    "Mst",
    "Mvt",
    "Src",
    "Ssm",
]


@xattree
class Gwt(Model):
    list_: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    dependent_variable_scaling: bool = field(block="options", default=False)
    dis: Dis | None = field(block="packages", default=None)
    ic: Ic | None = field(block="packages", default=None)
    adv: Adv | None = field(block="packages", default=None)
    dsp: Dsp | None = field(block="packages", default=None)
    mst: Mst | None = field(block="packages", default=None)
    cnc: list[Cnc] = field(block="packages")
    src: list[Src] = field(block="packages")
    ssm: Ssm | None = field(block="packages", default=None)
    mvt: Mvt | None = field(block="packages", default=None)
    api: Api | None = field(block="packages", default=None)
