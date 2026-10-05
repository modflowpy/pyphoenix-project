from typing import ClassVar, Optional

import attrs

from flopy4.mf6.model import Model
from flopy4.mf6.prt.dis import Dis
from flopy4.mf6.prt.disv import Disv
from flopy4.mf6.prt.fmi import Fmi
from flopy4.mf6.prt.mip import Mip
from flopy4.mf6.prt.oc import Oc
from flopy4.mf6.prt.prp import Prp
from flopy4.mf6.spec import child, field

__all__ = [
    "Prt",
    "Dis",
    "Disv",
    "Fmi",
    "Mip",
    "Oc",
    "Prp",
]


@attrs.define(kw_only=True, slots=False)
class Prt(Model):
    dfn_name: ClassVar[str] = "prt-nam"

    list_: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    dis: Dis | Disv | None = child(block="packages")
    fmi: Fmi | None = child(block="packages")
    mip: Mip | None = child(block="packages")
    oc: Oc | None = child(block="packages")
    prp: list[Prp] = child(block="packages", default=attrs.Factory(list))

    @property
    def grid(self):
        if self.dis is not None:
            return self.dis.to_grid()
