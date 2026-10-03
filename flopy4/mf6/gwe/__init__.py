from pathlib import Path
from typing import ClassVar, Optional

import attrs

from flopy4.mf6.gwe.adv import Adv
from flopy4.mf6.gwe.cnd import Cnd
from flopy4.mf6.gwe.ctp import Ctp
from flopy4.mf6.gwe.dis import Dis
from flopy4.mf6.gwe.disu import Disu
from flopy4.mf6.gwe.disv import Disv
from flopy4.mf6.gwe.esl import Esl
from flopy4.mf6.gwe.est import Est
from flopy4.mf6.gwe.ic import Ic
from flopy4.mf6.gwe.lke import Lke
from flopy4.mf6.gwe.mve import Mve
from flopy4.mf6.gwe.oc import Oc
from flopy4.mf6.gwe.ssm import Ssm
from flopy4.mf6.model import Model
from flopy4.mf6.spec import child, field, path
from flopy4.utils import to_path

__all__ = [
    "Gwe",
    "Dis",
    "Disu",
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


@attrs.define(kw_only=True, slots=False)
class Gwe(Model):
    dfn_name: ClassVar[str] = "gwe-nam"

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
    cnd: Cnd | None = child(block="packages")
    est: Est | None = child(block="packages")
    ctp: list[Ctp] = child(block="packages", default=attrs.Factory(list))
    esl: list[Esl] = child(block="packages", default=attrs.Factory(list))
    lke: list[Lke] = child(block="packages", default=attrs.Factory(list))
    ssm: Ssm | None = child(block="packages")
    mve: Mve | None = child(block="packages")

    @property
    def grid(self):
        if self.dis is not None:
            return self.dis.to_grid()
