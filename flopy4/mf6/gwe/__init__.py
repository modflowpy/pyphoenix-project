from typing import Optional

from xattree import xattree

from flopy4.mf6.gwe.adv import Adv
from flopy4.mf6.gwe.cnd import Cnd
from flopy4.mf6.gwe.ctp import Ctp
from flopy4.mf6.gwe.dis import Dis
from flopy4.mf6.gwe.esl import Esl
from flopy4.mf6.gwe.est import Est
from flopy4.mf6.gwe.ic import Ic
from flopy4.mf6.gwe.mve import Mve
from flopy4.mf6.gwe.oc import Oc
from flopy4.mf6.gwe.ssm import Ssm
from flopy4.mf6.model import Model
from flopy4.mf6.spec import field

__all__ = [
    "Gwe",
    "Dis",
    "Adv",
    "Cnd",
    "Ctp",
    "Esl",
    "Est",
    "Ic",
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
    dis: Dis | None = field(block="packages", default=None)
    ic: Ic | None = field(block="packages", default=None)
    adv: Adv | None = field(block="packages", default=None)
    cnd: Cnd | None = field(block="packages", default=None)
    est: Est | None = field(block="packages", default=None)
    ctp: list[Ctp] = field(block="packages")
    esl: list[Esl] = field(block="packages")
    ssm: Ssm | None = field(block="packages", default=None)
    mve: Mve | None = field(block="packages", default=None)
